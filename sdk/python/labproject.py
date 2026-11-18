"""Projekte und dauerhafte Umgebungen (A2, Architektur D1/D2).

Ablage (Wurzel = Umgebungsvariable FOLIO_SUITE_DIR, die der Hub setzt; sonst `<out>/suite` im Einzelbetrieb):

    suite.json                                   Projektliste und aktives Projekt (schreibt der Hub)
    projects/<projekt>/project.json              Name, Berichte (Folio-Projekt-IDs), angelegt
    projects/<projekt>/env/<modul>/<umgebung>/
        manifest.json                            ID, Name, Modul, angelegt, geändert, Rohdateien
        state.json                               Zustand des Moduls (Protokoll, Einstellungen, Auswahl)
        raw/<sha256[:16]>-<name>                 Rohdateien unverändert (gleicher Inhalt nur einmal)
        results/<n>.json                         Ergebnisversionen 1, 2, … (nie überschrieben)

Ein Standardprojekt und je Modul eine Standardumgebung entstehen automatisch, damit einfache Arbeit keine
Einrichtung braucht. Persönliche Bibliotheken, eigene Stoffe und Gleichungen bleiben projektübergreifend in
`outputs/<modul>/` (Q21 = a) und gehören nicht hierher.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_PROJECT = "standard"
DEFAULT_ENV = "standard"
_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
_SAFE = re.compile(r"[^A-Za-z0-9._ -]+")


class EnvError(ValueError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read(p: Path, default=None):
    try:
        return json.loads(p.read_text("utf-8"))
    except (OSError, ValueError):
        return default


def _write(p: Path, data) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + f".{secrets.token_hex(3)}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
    os.replace(tmp, p)                                                # atomar: nie halb geschriebene Dateien


def _check_id(x: str, what: str) -> str:
    if not isinstance(x, str) or not _ID.match(x):
        raise EnvError(f"ungültige {what}-ID")
    return x


def suite_root(out_dir: str | Path | None = None) -> Path:
    env = os.environ.get("FOLIO_SUITE_DIR")
    if env:
        return Path(env)
    return Path(out_dir or ".") / "suite"


class Suite:
    """Projektliste. Der Hub pflegt sie; Module lesen nur das aktive Projekt (oder legen den Standard an)."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    @property
    def registry(self) -> dict:
        reg = _read(self.root / "suite.json")
        if not isinstance(reg, dict) or not reg.get("projects"):
            reg = {"version": 1, "active": DEFAULT_PROJECT,
                   "projects": [{"id": DEFAULT_PROJECT, "name": "Standardprojekt", "reports": [], "created": _now()}]}
            _write(self.root / "suite.json", reg)
        return reg

    def active(self) -> str:
        reg = self.registry
        ids = {p["id"] for p in reg["projects"]}
        a = reg.get("active")
        return a if a in ids else reg["projects"][0]["id"]

    def project_dir(self, pid: str | None = None) -> Path:
        pid = _check_id(pid or self.active(), "Projekt")
        d = self.root / "projects" / pid
        if not (d / "project.json").exists():
            p = next((x for x in self.registry["projects"] if x["id"] == pid), None)
            if p is None:
                raise EnvError("Projekt nicht gefunden")
            _write(d / "project.json", p)
        return d


class Environments:
    """Umgebungen eines Moduls im aktiven (oder angegebenen) Projekt."""

    def __init__(self, suite: Suite, module: str, project: str | None = None):
        self.suite = suite
        self.module = _check_id(module, "Modul")
        self.project = project

    @property
    def base(self) -> Path:
        return self.suite.project_dir(self.project) / "env" / self.module

    def _dir(self, eid: str) -> Path:
        d = self.base / _check_id(eid, "Umgebungs")
        if eid == DEFAULT_ENV and not (d / "manifest.json").exists():
            self._make(DEFAULT_ENV, "Standard")
        if not (d / "manifest.json").exists():
            raise EnvError("Umgebung nicht gefunden")
        return d

    def list(self) -> list[dict]:
        if not (self.base / DEFAULT_ENV / "manifest.json").exists():
            self._make(DEFAULT_ENV, "Standard")
        out = []
        for d in sorted(self.base.iterdir()):
            m = _read(d / "manifest.json")
            if isinstance(m, dict) and not d.name.startswith("_"):
                out.append(m)
        out.sort(key=lambda m: (m["id"] != DEFAULT_ENV, m.get("created", "")))
        return out

    def _make(self, eid: str, name: str) -> dict:
        m = {"id": eid, "name": name, "module": self.module, "created": _now(), "modified": _now(), "raw": {}}
        _write(self.base / eid / "manifest.json", m)
        return m

    def manifest(self, eid: str) -> dict:
        return _read(self._dir(eid) / "manifest.json")

    def create(self, name: str) -> dict:
        name = (name or "").strip()[:80] or "Neue Umgebung"
        self.list()
        return self._make(secrets.token_hex(4), name)

    def rename(self, eid: str, name: str) -> dict:
        m = self.manifest(eid)
        m["name"] = (name or "").strip()[:80] or m["name"]
        m["modified"] = _now()
        _write(self._dir(eid) / "manifest.json", m)
        return m

    def delete(self, eid: str) -> None:
        """In den Papierkorb `_papierkorb/` verschieben (nicht endgültig löschen); die Standardumgebung bleibt."""
        if eid == DEFAULT_ENV:
            raise EnvError("Die Standardumgebung kann nicht gelöscht werden")
        d = self._dir(eid)
        trash = self.base / "_papierkorb"
        trash.mkdir(parents=True, exist_ok=True)
        shutil.move(str(d), str(trash / f"{eid}-{datetime.now().strftime('%Y%m%d%H%M%S')}"))

    # ------------------------------------------------------------------ Zustand
    def save_state(self, eid: str, state) -> None:
        d = self._dir(eid)
        _write(d / "state.json", state)
        m = _read(d / "manifest.json")
        m["modified"] = _now()
        _write(d / "manifest.json", m)

    def load_state(self, eid: str, default=None):
        return _read(self._dir(eid) / "state.json", default)

    # ------------------------------------------------------------------ Rohdateien
    def add_raw(self, eid: str, name: str, data: bytes) -> str:
        """Rohdatei ablegen; Rückgabe ist ihre ID (sha256-Anfang + Name). Gleicher Inhalt wird nicht doppelt gespeichert."""
        d = self._dir(eid)
        sha = hashlib.sha256(data).hexdigest()
        safe = _SAFE.sub("_", Path(name).name)[:80] or "datei"
        rid = f"{sha[:16]}-{safe}"
        p = d / "raw" / rid
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data)
        m = _read(d / "manifest.json")
        raws = m.setdefault("raw", {})
        raws[rid] = {"name": name, "sha256": sha, "bytes": len(data), "added": raws.get(rid, {}).get("added", _now())}
        m["modified"] = _now()
        _write(d / "manifest.json", m)
        return rid

    def raw(self, eid: str, rid: str) -> bytes:
        if "/" in rid or "\\" in rid or rid.startswith("."):
            raise EnvError("ungültige Datei-ID")
        p = self._dir(eid) / "raw" / rid
        if not p.exists():
            raise EnvError("Rohdatei nicht gefunden")
        return p.read_bytes()

    def drop_raw(self, eid: str, keep: set[str]) -> None:
        """Rohdateien, die der Zustand nicht mehr nennt, aus dem Manifest nehmen (Datei bleibt, falls ein Ergebnis sie nennt)."""
        d = self._dir(eid)
        m = _read(d / "manifest.json")
        used = set()
        for r in (d / "results").glob("*.json") if (d / "results").exists() else []:
            used |= set((_read(r) or {}).get("raw", []))
        # A8: Rohdateien hinter geteilten Versionen bleiben (Herkunftskette), auch wenn der Eintrag geschlossen wird
        sb = self.suite.project_dir(self.project) / "sharebox"
        for v in sb.glob("*/v*.json") if sb.exists() else []:
            p = (_read(v) or {}).get("producer") or {}
            if p.get("module") == self.module and p.get("env") == eid and p.get("raw"):
                used.add(p["raw"])
        for rid in list(m.get("raw", {})):
            if rid not in keep:
                m["raw"].pop(rid)
                if rid not in used:
                    (d / "raw" / rid).unlink(missing_ok=True)
        _write(d / "manifest.json", m)

    # ------------------------------------------------------------------ Ergebnisversionen
    def add_result(self, eid: str, payload: dict, raw: list[str] | None = None) -> int:
        d = self._dir(eid) / "results"
        d.mkdir(parents=True, exist_ok=True)
        n = 1 + max((int(p.stem) for p in d.glob("*.json") if p.stem.isdigit()), default=0)
        _write(d / f"{n}.json", {"version": n, "created": _now(), "raw": list(raw or []), "payload": payload})
        return n

    def results(self, eid: str) -> list[dict]:
        d = self._dir(eid) / "results"
        if not d.exists():
            return []
        out = [_read(p) for p in d.glob("*.json") if p.stem.isdigit()]
        return sorted((r for r in out if r), key=lambda r: r["version"])


MAX_CLIENT = 5 * 1024 * 1024
MAX_SUMMARY = 48 * 1024          # UI-15: Wertekatalog (≤ 80 Werte); UI-18: kleine Grafiken (labenv.js kürzt auf 46 000)
ENV_VALUES = "lab.envvalues"     # Werte Umgebung → Umgebung (alle Module ausser dem Elementrechner)
ENV_VALUE_KINDS = (ENV_VALUES, "chem.envvalues")


class ModuleEnvs:
    """Aktive Umgebung eines Modulservers: geladene Dateien (als Rohdatei + Index) und der Seitenzustand.

    Zustand einer Umgebung: {"items": {iid: {raw, file, idx, name}}, "client": <JSON der Seite>}.
    Nach einem Neustart liefert `stored()` die Dateien zurück; der Server liest sie mit seinem eigenen Leser neu ein,
    die Seite stellt ihren Zustand aus `client` wieder her.
    """

    def __init__(self, out_dir, module: str):
        import threading
        self.suite = Suite(suite_root(out_dir))
        self.module = _check_id(module, "Modul")
        self.project: str | None = None
        self.eid: str | None = None
        self.items: dict = {}
        self.client = None
        self.lock = threading.RLock()

    @property
    def envs(self) -> Environments:
        return Environments(self.suite, self.module, self.project)

    def ensure(self) -> bool:
        """Aktives Projekt und dessen zuletzt benutzte Umgebung laden; True, wenn neu geladen wurde."""
        with self.lock:
            pid = self.suite.active()
            if pid == self.project and self.eid:
                return False
            self.project = pid
            envs = self.envs
            envs.list()
            eid = (_read(envs.base / "_aktiv.json", {}) or {}).get("id", DEFAULT_ENV)
            try:
                envs.manifest(eid)
            except EnvError:
                eid = DEFAULT_ENV
            self._load(eid)
            return True

    def _load(self, eid: str) -> None:
        st = self.envs.load_state(eid, {}) or {}
        self.eid = eid
        self.items = st.get("items") if isinstance(st.get("items"), dict) else {}
        self.client = st.get("client")
        _write(self.envs.base / "_aktiv.json", {"id": eid})

    def _save(self) -> None:
        self.envs.save_state(self.eid, {"items": self.items, "client": self.client})

    def remember(self, iid: str, raw: bytes, fname: str, idx: int = 0, name: str | None = None, **extra) -> None:
        """Geladene Datei merken; `extra` (JSON) nimmt Modulangaben auf, z. B. die Spaltenzuordnung."""
        with self.lock:
            self.ensure()
            rid = self.envs.add_raw(self.eid, fname, raw)
            self.items[iid] = {"raw": rid, "file": fname, "idx": int(idx), "name": name, "extra": extra}
            self._save()

    def replace_raw(self, iid: str, raw: bytes, fname: str | None = None, name: str | None = None) -> str:
        """DP-M1: new content for an entry that is edited in the page (manual sheet), or a connected dataset that
        follows its source. The previous raw file goes, unless a result or share version still names it (provenance)."""
        with self.lock:
            self.ensure()
            if iid not in self.items:
                raise EnvError("Eintrag nicht in dieser Umgebung")
            v = self.items[iid]
            v["raw"] = self.envs.add_raw(self.eid, fname or v["file"], raw)
            if fname:
                v["file"] = fname
            if name:
                v["name"] = name
            self._save()
            self.envs.drop_raw(self.eid, {x["raw"] for x in self.items.values()})
            return v["raw"]

    def set_extra(self, iid: str, **extra) -> None:
        with self.lock:
            if iid in self.items:
                self.items[iid].setdefault("extra", {}).update(extra)
                self._save()

    def forget(self, iid: str) -> None:
        with self.lock:
            self.ensure()
            if self.items.pop(iid, None) is not None:
                self._save()
                self.envs.drop_raw(self.eid, {v["raw"] for v in self.items.values()})

    def set_name(self, iid: str, name: str) -> None:
        with self.lock:
            if iid in self.items:
                self.items[iid]["name"] = name
                self._save()

    def set_client(self, client) -> None:
        if len(json.dumps(client, ensure_ascii=False)) > MAX_CLIENT:
            raise EnvError("Seitenzustand zu gross zum Speichern")
        with self.lock:
            self.ensure()
            self.client = client
            self._save()
            # UI-10: kurze Zusammenfassung ins Manifest, damit die Übersicht jede Umgebung zeigen kann, ohne sie zu öffnen
            summ = client.get("summary") if isinstance(client, dict) else None
            if isinstance(summ, dict) and len(json.dumps(summ, ensure_ascii=False)) <= MAX_SUMMARY:
                d = self.envs._dir(self.eid)
                m = _read(d / "manifest.json")
                if m.get("summary") != summ:
                    m["summary"] = summ
                    _write(d / "manifest.json", m)

    # ------------------------------------------------------------------ Übersicht (UI-10)
    def board(self) -> dict:
        """Lage der Kästen und Verbindungen der Übersicht dieses Moduls im aktiven Projekt."""
        with self.lock:
            self.ensure()
            b = _read(self.envs.base / "_board.json", {}) or {}
            return {"pos": b.get("pos") or {}, "links": b.get("links") or []}

    def set_board(self, b: dict) -> dict:
        def num(v):
            x = float(v)
            if x != x or abs(x) > 1e6:
                raise ValueError
            return round(x, 1)
        pos = {}
        for k, v in list((b.get("pos") or {}).items())[:500]:
            try:
                pos[str(k)[:80]] = [num(v[0]), num(v[1])]
            except (TypeError, ValueError, IndexError):
                continue
        links = []
        for ln in (b.get("links") or [])[:500]:
            if not isinstance(ln, dict) or not ln.get("from") or not ln.get("to"):
                continue
            e = {"from": str(ln["from"])[:80], "to": str(ln["to"])[:80]}
            if ln.get("mode") in ("pin", "live", "copy"):
                e["mode"] = ln["mode"]
            if isinstance(ln.get("version"), int):
                e["version"] = ln["version"]
            if ln.get("kind"):
                e["kind"] = str(ln["kind"])[:40]
            if ln.get("share"):                                      # UI-15: Werte Umgebung → Umgebung
                e["share"] = str(ln["share"])[:40]
            if isinstance(ln.get("keys"), list):
                e["keys"] = [str(k)[:60] for k in ln["keys"][:80] if isinstance(k, str) and k]
            links.append(e)
        with self.lock:
            self.ensure()
            _write(self.envs.base / "_board.json", {"pos": pos, "links": links, "modified": _now()})
        return {"pos": pos, "links": links}

    def stored(self):
        """[(iid, Rohdaten, Dateiname, Index, Name, extra)] der aktiven Umgebung; fehlende Rohdateien werden
        übersprungen."""
        with self.lock:
            self.ensure()
            out = []
            for iid, v in list(self.items.items()):
                try:
                    out.append((iid, self.envs.raw(self.eid, v["raw"]), v["file"], v.get("idx", 0), v.get("name"),
                                v.get("extra") or {}))
                except (EnvError, KeyError):
                    continue
            return out

    def info(self) -> dict:
        with self.lock:
            self.ensure()
            reg = self.suite.registry
            p = next((x for x in reg["projects"] if x["id"] == self.project), {"id": self.project, "name": self.project})
            return {"project": {"id": p["id"], "name": p.get("name")}, "envs": self.envs.list(), "active": self.eid}

    # Umgebungen verwalten
    def switch(self, eid: str) -> None:
        with self.lock:
            self.ensure()
            self.envs.manifest(eid)
            self._load(eid)

    def create(self, name: str) -> str:
        with self.lock:
            self.ensure()
            m = self.envs.create(name)
            self._load(m["id"])
            return m["id"]

    def rename(self, eid: str, name: str) -> None:
        with self.lock:
            self.ensure()
            self.envs.rename(eid, name)

    def delete(self, eid: str) -> None:
        with self.lock:
            self.ensure()
            from labprov import guard_env_delete          # A8: Umgebung hinter einer im Bericht benutzten Version bleibt
            guard_env_delete(self.suite, self.project, self.module, eid)
            self.envs.delete(eid)
            if eid == self.eid:
                self._load(DEFAULT_ENV)

    def board_shares(self) -> dict:
        """Kästen der Übersicht: Freigaben anderer Module an dieses Modul (nur lesen) und eigene Freigaben.
        Nur Kopfdaten, keine Messwerte."""
        from labshare import Sharebox
        self.ensure()
        keys = ("id", "kind", "title", "latest", "producer", "recipients", "modified")
        every = Sharebox(self.suite, self.project).list()
        mine = lambda m: (m.get("producer") or {}).get("module") == self.module  # noqa: E731
        slim = lambda m: {k: m.get(k) for k in keys}  # noqa: E731
        ev = lambda m: m.get("kind") in ENV_VALUE_KINDS  # noqa: E731
        return {"incoming": [slim(m) for m in every if self.module in (m.get("recipients") or []) and not mine(m)],
                "own": [slim(m) for m in every if mine(m) and not ev(m)],
                "envvalues": [slim(m) for m in every if mine(m) and ev(m)]}     # Umgebung → Umgebung (Verbindungen)

    def publish_env_values(self, env_id: str, items: list, module_version: str = "") -> dict:
        """Werte einer Umgebung für andere Umgebungen desselben Moduls (Verbindung auf der Übersicht, kind env.values).

        Eine Freigabe je Quellumgebung (kind lab.envvalues); eine neue Version entsteht nur, wenn sich ein Wert
        (Schlüssel, Zahl, Einheit, Bezeichnung) geändert hat. Live-Verbindungen folgen der neuesten Version,
        Momentaufnahmen behalten ihre."""
        from labshare import Sharebox
        self.ensure()
        known = {e["id"]: e["name"] for e in self.envs.list()}
        if env_id not in known:
            raise EnvError("Unbekannte Umgebung")
        outs = []
        for it in (items or [])[:200]:
            if not isinstance(it, dict) or not str(it.get("sym") or "").strip():
                continue
            try:
                v = float(str(it.get("value", "")).replace(",", ".").replace("−", "-"))
            except (TypeError, ValueError):
                continue
            if v != v or v in (float("inf"), float("-inf")):
                continue
            outs.append({"key": str(it["sym"]).strip()[:60], "label": str(it.get("label") or it["sym"])[:200],
                         "quantity": {"value": v, "unit": str(it.get("unit") or "")[:40]},
                         "conditions": {"kind": str(it.get("kind") or "")[:40]}})
        if not outs:
            raise EnvError("Keine Zahlenwerte zum Teilen")
        box = Sharebox(self.suite, self.project)
        prev = next((m for m in box.list(kind=ENV_VALUES) if (m.get("producer") or {}).get("module") == self.module
                     and (m.get("producer") or {}).get("env") == env_id), None)
        if prev:
            last = box.get(prev["id"], prev["latest"])
            sig = lambda os: sorted((o["key"], o["quantity"]["value"], o["quantity"].get("unit", ""), o.get("label", "")) for o in os)  # noqa: E731
            if sig(last.get("outputs") or []) == sig(outs):
                return {**last, "unchanged": True}
        prod = {"module": self.module, "env": env_id, "env_name": known[env_id], "item": "umgebungswerte",
                "item_name": "Werte der Umgebung", "module_version": module_version}
        return box.publish(prod, ENV_VALUES, f"Werte aus „{known[env_id]}“", outs, [self.module],
                           share_id=prev["id"] if prev else None)

    def board_share(self, share_id: str, version=None) -> dict:
        """Eine Freigabe lesen: an dieses Modul gerichtet oder eigene. Andere bleiben verborgen."""
        from labshare import Sharebox
        self.ensure()
        box = Sharebox(self.suite, self.project)
        head = next((m for m in box.list() if m.get("id") == share_id), None)
        own = bool(head) and (head.get("producer") or {}).get("module") == self.module
        return box.get(share_id, int(version) if version else None, None if own else self.module)

    def datasets(self) -> dict:
        """I-01/I-02: alle Datensätze (`data.table`) des Projekts für das Import-Fenster, die an dieses Modul gerichteten
        zuerst (sonst neueste zuerst). Nur Kopfdaten."""
        from labshare import DATA_KIND, Sharebox, for_me
        self.ensure()
        box = Sharebox(self.suite, self.project)
        out = []
        for m in box.list(self.module, DATA_KIND):
            try:
                env = box.get(m["id"], None, self.module)
            except EnvError:
                continue
            h, p = env.get("dataset") or {}, m.get("producer") or {}
            out.append({"id": m["id"], "title": m.get("title"), "latest": m.get("latest"), "modified": m.get("modified"),
                        "rows": h.get("rows"), "derived": bool(m.get("derive")), "for_me": for_me(m, self.module),
                        "producer": {k: p.get(k) for k in ("module", "env", "env_name", "item_name")},
                        "columns": [{k: c.get(k) for k in ("key", "name", "unit", "kind", "dtype", "role")}
                                    for c in h.get("columns") or []]})
        out.sort(key=lambda d: not d["for_me"])                 # stabil: innerhalb der Gruppen neueste zuerst
        return {"datasets": out, "module": self.module}

    def dataset_preview(self, share_id: str, version=None) -> dict:
        """I-02: Vorschau eines Datensatzes: Versionen, Spalten mit Wertebereich, kleines Bild, die ersten Zeilen."""
        import math
        import numpy as np
        from labdataset import thumb
        from labshare import Sharebox, dataset_of, for_me
        self.ensure()
        box = Sharebox(self.suite, self.project)
        env = box.get(share_id, int(version) if version else None, self.module)
        d = box.base / share_id
        ds = dataset_of(env, d)
        head = _read(d / "share.json") or {}
        versions = []
        for f in d.glob("v*.json"):
            if f.stem[1:].isdigit():
                e = _read(f) or {}
                versions.append({"version": int(f.stem[1:]), "created": e.get("created"),
                                 "rows": (e.get("dataset") or {}).get("rows")})
        versions.sort(key=lambda v: -v["version"])
        used = ds.used_mask()
        ext = {}
        for c in ds.columns:
            if c.get("dtype") == "number":
                a = np.asarray(ds.values(c["key"]), float)[used]
                a = a[np.isfinite(a)]
                ext[c["key"]] = [float(a.min()), float(a.max()), int(a.size)] if a.size else None
        cell = lambda x: (x if math.isfinite(x) else None) if isinstance(x, float) else str(x)[:60]  # noqa: E731
        n = min(ds.rows, 8)
        keys = [c["key"] for c in ds.columns][:12]
        first = {k: [cell(x) for x in ds.values(k)[:n].tolist()] for k in keys}
        try:
            th = thumb(ds)
        except Exception:                                        # das Bild ist Beiwerk
            th = None
        p = env.get("producer") or {}
        return {"id": share_id, "title": env.get("title"), "version": env["version"], "latest": head.get("latest"),
                "rows": ds.rows, "excluded": int((~used).sum()), "for_me": for_me(head, self.module),
                "derived": bool(head.get("derive")), "created": env.get("created"),
                "producer": {k: p.get(k) for k in ("module", "env", "env_name", "item_name")},
                "columns": [{k: c.get(k) for k in ("key", "name", "unit", "kind", "dtype", "role")} for c in ds.columns],
                "ext": ext, "first": {"keys": keys, "n": n, "values": first}, "versions": versions[:40], "thumb": th}

    def route(self, action: str, req: dict, reload) -> dict:
        """Gemeinsame Endpunkte /api/env/<action>. `reload()` lädt die gespeicherten Dateien in den Server und gibt die
        Beschreibungen der Einträge zurück (modulspezifisch)."""
        if action == "datasets":                       # I-02: Import-Fenster – Liste aller Datensätze des Projekts
            return self.datasets()
        if action == "dataset":                        # I-02: Vorschau eines Datensatzes
            return self.dataset_preview(str(req.get("id") or ""), req.get("version"))
        if action == "open":
            changed = self.ensure()
            if req.get("check") and not changed:
                return {"changed": False}
            return {"changed": True, **self.info(), "items": reload(), "client": self.client}
        if action == "client":
            self.set_client(req.get("client"))
            return {"ok": True}
        if action == "info":
            return self.info()
        if action == "board":                          # UI-10: lesen; mit "board" speichern
            return self.set_board(req["board"]) if isinstance(req.get("board"), dict) else self.board()
        if action == "shares":                         # UI-04…09: Freigaben für die Übersicht (nur Kopfdaten)
            return self.board_shares()
        if action == "share":                          # eine Freigabe (Umschlag) für die Übernahme
            return self.board_share(str(req.get("id") or ""), req.get("version"))
        if action == "envvalues":                      # Werte an andere Umgebungen (Verbindung auf der Übersicht)
            return self.publish_env_values(str(req.get("env") or ""), req.get("items") or [],
                                           str(req.get("module_version") or ""))
        if action in ("switch", "create", "rename", "delete"):
            if action == "switch":
                self.switch(str(req.get("id", "")))
            elif action == "create":
                self.create(str(req.get("name", "")))
            elif action == "rename":
                self.rename(str(req.get("id", "")), str(req.get("name", "")))
                return self.info()
            else:
                self.delete(str(req.get("id", "")))
            return {"changed": True, **self.info(), "items": reload(), "client": self.client}
        raise EnvError("unbekannte Umgebungsaktion")
