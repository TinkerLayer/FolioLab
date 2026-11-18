"""Geteilte Ergebnisse (A3): Umschlag `suite.shared-result/1` und Sharebox je Projekt.

Ein Modul veröffentlicht *ausgewählte* Ergebnisse einer Umgebung (nie Rohdaten) für genannte Empfänger-Module.
Jede Veröffentlichung bekommt eine neue Version; alte Versionen bleiben lesbar (Architektur §3, Regeln 1–4).
Versionsnummern werden nie zweimal vergeben: share.json hält die höchste je vergebene Nummer (`issued`) und je
gelöschter Version einen Grabstein (`deleted`: Nummer, Zeit, Prüfsumme). Löschen wird verweigert, solange ein
Bericht die Version (oder einen daraus abgeleiteten Datensatz) benutzt (`labprov.guard_share_delete`).

Ablage im Projekt:  sharebox/<share-id>/share.json    Erzeuger, Titel, Empfänger, Art, issued, deleted
                    sharebox/<share-id>/v<n>.json       Umschlag der Version n (unveränderlich)

Umschlag:
    {"schema": "suite.shared-result/1", "id": "<share-id>", "version": n, "created": ISO,
     "producer": {"module", "env", "env_name", "item", "item_name", "module_version"},
     "kind": "tga.steps", "title": "...",
     "outputs": [{"key", "label", "quantity": {"value", "unit", "u"?}, "conditions"?: {...}}, ...],
     "sources": [...], "hash": sha256 über outputs}

Empfänger binden *gepinnt* (feste Version) oder als *Kopie* (Umschlag wird in ihren Zustand übernommen).

Ausnahme Datensätze (DP-02): die Art `data.table` trägt einen ganzen Datensatz (`suite.dataset/1`, siehe
`labdataset`). Der Umschlag enthält dessen Kopf (`dataset`) und als `outputs` nur Zeilen- und Spaltenzahl; die Werte
liegen daneben in `v<n>.npz` (`data`). `hash` ist die Prüfsumme des Datensatzes. Nur `publish_dataset` erzeugt
diese Art; alle anderen Arten bleiben reine Zahlen (Regel 1).

I-01: Datensätze darf jedes Modul des Projekts lesen (Import aus jedem Werkzeug). Die Empfänger einer `data.table`
markieren nur, für welche Module der Datensatz gedacht ist („für dieses Modul“ steht im Import oben).
"""
from __future__ import annotations

import hashlib
import json
import secrets
from pathlib import Path

from labproject import EnvError, Suite, _check_id, _now, _read, _write

SCHEMA = "suite.shared-result/1"
MAX_OUTPUTS = 200
DATA_KIND = "data.table"
MAX_DATA_BYTES = 200 * 1024 * 1024      # Grenze für die Datei neben dem Umschlag (komprimiert)


def readable(meta: dict, recipient: str | None) -> bool:
    """Darf `recipient` diese Freigabe lesen? Datensätze (I-01) jedes Modul, sonst nur die genannten Empfänger."""
    return not recipient or meta.get("kind") == DATA_KIND or recipient in (meta.get("recipients") or [])


def for_me(meta: dict, module: str) -> bool:
    """I-01: ausdrücklich an dieses Modul gerichtet (im Import oben einsortiert)."""
    return module in (meta.get("recipients") or [])


def _hash(outputs) -> str:
    return hashlib.sha256(json.dumps(outputs, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def check_outputs(outputs) -> list[dict]:
    """Nur Zahlen mit Einheit und kurze Texte; keine Kurven oder Rohdaten (Regel 1)."""
    if not isinstance(outputs, list) or not outputs:
        raise EnvError("Keine Ergebnisse zum Teilen gewählt")
    if len(outputs) > MAX_OUTPUTS:
        raise EnvError("Zu viele Ergebnisse auf einmal")
    out = []
    for o in outputs:
        q = (o or {}).get("quantity") or {}
        v = q.get("value")
        if not isinstance(v, (int, float)) or isinstance(v, bool) or v != v:
            raise EnvError(f"{o.get('key', '?')}: Wert fehlt oder ist keine Zahl")
        rec = {"key": str(o.get("key", ""))[:60], "label": str(o.get("label", ""))[:160],
               "quantity": {"value": float(v), "unit": str(q.get("unit", ""))[:20]}}
        if isinstance(q.get("u"), (int, float)):
            rec["quantity"]["u"] = float(q["u"])
        cond = o.get("conditions")
        if isinstance(cond, dict):
            rec["conditions"] = {str(k)[:40]: (c[:200] if isinstance(c, str) else c)
                                 for k, c in list(cond.items())[:20]
                                 if isinstance(c, (int, float, str)) and not isinstance(c, bool)}
        out.append(rec)
    return out


class Sharebox:
    def __init__(self, suite: Suite, project: str | None = None):
        self.suite = suite
        self.project = project

    @property
    def base(self) -> Path:
        return self.suite.project_dir(self.project) / "sharebox"

    def publish(self, producer: dict, kind: str, title: str, outputs, recipients, sources=None,
                share_id: str | None = None) -> dict:
        """Neue Version veröffentlichen; ohne share_id entsteht eine neue Freigabe."""
        if str(kind) == DATA_KIND:
            raise EnvError("Datensätze werden mit publish_dataset geteilt")
        return self._publish(producer, kind, title, check_outputs(outputs), recipients, sources, share_id)

    def publish_dataset(self, producer: dict, title: str, dataset, recipients, sources=None,
                        share_id: str | None = None) -> dict:
        """DP-02: einen geprüften Datensatz (labdataset.Dataset) als Art `data.table` teilen."""
        from labdataset import Dataset
        if not isinstance(dataset, Dataset):
            raise EnvError("Kein Datensatz")
        h = dataset.header
        outs = check_outputs([{"key": "rows", "label": "Zeilen", "quantity": {"value": h["rows"], "unit": ""}},
                              {"key": "columns", "label": "Spalten", "quantity": {"value": len(h["columns"]), "unit": ""}}])

        def write(d: Path, n: int) -> dict:
            stem = d / f"v{n}"
            dataset.save(stem)
            stem.with_suffix(".json").unlink()          # der Kopf steht im Umschlag
            size = stem.with_suffix(".npz").stat().st_size
            if size > MAX_DATA_BYTES:
                stem.with_suffix(".npz").unlink()
                raise EnvError(f"Datensatz zu gross zum Teilen ({size // 1048576} MB)")
            return {"dataset": h, "data": stem.with_suffix(".npz").name, "hash": h["data_hash"]}

        return self._publish(producer, DATA_KIND, title, outs, recipients, sources, share_id, write)

    def _publish(self, producer, kind, title, outs, recipients, sources, share_id, write=None) -> dict:
        rec = [_check_id(r, "Modul") for r in recipients or []]
        if not rec:
            raise EnvError("Kein Empfänger gewählt")
        if share_id:
            d = self.base / _check_id(share_id, "Freigabe")
            meta = _read(d / "share.json")
            if not meta:
                raise EnvError("Freigabe nicht gefunden")
            if meta["producer"]["module"] != producer.get("module"):
                raise EnvError("Nur das erzeugende Modul darf eine neue Version veröffentlichen")
            if (meta.get("kind") == DATA_KIND) != (str(kind) == DATA_KIND):
                raise EnvError("Eine Freigabe bleibt bei ihrer Art (Datensatz oder Zahlen)")
        else:
            share_id = "s-" + secrets.token_hex(4)
            d = self.base / share_id
            meta = {"id": share_id, "created": _now()}
        # A8: a version number is never given twice, also after a version was deleted (share.json keeps the highest
        # number ever issued and a tombstone per deleted version)
        n = 1 + max([int(p.stem[1:]) for p in d.glob("v*.json") if p.stem[1:].isdigit()]
                    + [int(meta.get("issued") or 0)] + [int(t.get("version") or 0) for t in meta.get("deleted") or []])
        env = {"schema": SCHEMA, "id": share_id, "version": n, "created": _now(),
               "producer": {k: producer.get(k) for k in ("module", "env", "env_name", "item", "item_name", "module_version", "raw")},
               "kind": str(kind)[:40], "title": str(title)[:160], "outputs": outs,
               "sources": list(sources or [])[:20], "hash": _hash(outs)}
        if write:
            d.mkdir(parents=True, exist_ok=True)
            env.update(write(d, n))
        meta.update({"producer": env["producer"], "kind": env["kind"], "title": env["title"], "recipients": rec,
                     "latest": n, "issued": n, "modified": env["created"]})
        _write(d / f"v{n}.json", env)
        _write(d / "share.json", meta)
        return env

    def list(self, recipient: str | None = None, kind: str | None = None) -> list[dict]:
        if not self.base.exists():
            return []
        out = []
        for d in sorted(self.base.iterdir()):
            m = _read(d / "share.json")
            if not isinstance(m, dict):
                continue
            if not readable(m, recipient):
                continue
            if kind and m.get("kind") != kind:
                continue
            out.append(m)
        out.sort(key=lambda m: m.get("modified", ""), reverse=True)
        return out

    def delete(self, share_id: str, version: int | None = None) -> None:
        """A8: eine Version (oder die ganze Freigabe) entfernen – verweigert, wenn ein Bericht sie (oder einen daraus
        abgeleiteten Datensatz) benutzt. Eine gelöschte Version hinterlässt einen Grabstein in share.json (Nummer,
        Zeit, Prüfsumme); ihre Nummer wird nie wieder vergeben. Die ganze Freigabe zu löschen entfernt den Ordner;
        eine neue Freigabe bekommt immer eine neue Kennung."""
        from labprov import guard_share_delete
        d = self.base / _check_id(share_id, "Freigabe")
        meta = _read(d / "share.json")
        if not meta:
            raise EnvError("Freigabe nicht gefunden")
        guard_share_delete(self.suite, self.project, share_id, version)
        if version is None:
            import shutil
            shutil.rmtree(d)
            return
        p = d / f"v{int(version)}.json"
        if not p.exists():
            raise EnvError(f"Version {version} nicht gefunden")
        old = _read(p) or {}
        p.unlink()
        side = d / f"v{int(version)}.npz"
        if side.exists():
            side.unlink()
        left = sorted(int(x.stem[1:]) for x in d.glob("v*.json") if x.stem[1:].isdigit())
        if not left:
            import shutil
            shutil.rmtree(d)
            return
        meta["issued"] = max(int(meta.get("issued") or 0), int(meta.get("latest") or 0), int(version))
        meta["deleted"] = (meta.get("deleted") or []) + [{"version": int(version), "deleted": _now(),
                                                          "hash": old.get("hash"), "created": old.get("created")}]
        meta["latest"] = left[-1]
        _write(d / "share.json", meta)

    def resolve(self, binding: dict, recipient: str | None = None) -> dict:
        """A4: Bindung auflösen. binding = {id, mode: pin|copy|live, version?, used?, copy?}.

        Ergebnis {status, envelope, latest, used}; status:
          current  – gebundene Version ist die neueste (bei live: Ergebnis mit der neuesten gerechnet)
          update   – gepinnt/Kopie, eine neuere Version ist verfügbar (Bindung bleibt, bis der Nutzer wechselt)
          stale    – live, eine neuere Version ist da, das Ergebnis wurde noch mit `used` gerechnet
          failed   – Freigabe oder Version fehlt; eine Kopie bleibt trotzdem nutzbar
        Live folgt nur gültigen Versionen: veröffentlicht wird ohnehin nur, was `check_outputs` besteht (Regel 7).
        """
        mode = binding.get("mode", "pin")
        used = binding.get("used") or binding.get("version")
        try:
            meta = _read(self.base / _check_id(binding.get("id") or "", "Freigabe") / "share.json")
        except EnvError:
            meta = None
        latest = (meta or {}).get("latest")
        if mode == "copy" and isinstance(binding.get("copy"), dict):
            env = binding["copy"]
            st = "update" if latest and latest > env.get("version", 0) else "current"
            return {"status": st, "envelope": env, "latest": latest, "used": env.get("version")}
        if not meta:
            return {"status": "failed", "envelope": None, "latest": None, "used": used,
                    "error": "Freigabe nicht mehr vorhanden"}
        try:
            if mode == "live":
                env = self.get(binding["id"], None, recipient)
                st = "stale" if used and used < env["version"] else "current"
                return {"status": st, "envelope": env, "latest": latest, "used": used}
            env = self.get(binding["id"], int(binding.get("version") or latest), recipient)
        except EnvError as e:
            return {"status": "failed", "envelope": None, "latest": latest, "used": used, "error": str(e)}
        return {"status": "update" if latest > env["version"] else "current", "envelope": env, "latest": latest,
                "used": env["version"]}

    def get(self, share_id: str, version: int | None = None, recipient: str | None = None) -> dict:
        d = self.base / _check_id(share_id, "Freigabe")
        m = _read(d / "share.json")
        if not m:
            raise EnvError("Freigabe nicht gefunden")
        if not readable(m, recipient):
            raise EnvError("Diese Freigabe ist nicht für dieses Modul bestimmt")
        v = int(version or m["latest"])
        env = _read(d / f"v{v}.json")
        if not env:
            t = next((t for t in m.get("deleted") or [] if t.get("version") == v), None)
            raise EnvError(f"Version {v} wurde am {str(t.get('deleted'))[:10]} gelöscht" if t else f"Version {v} nicht gefunden")
        return env

    def dataset(self, share_id: str, version: int | None = None, recipient: str | None = None):
        """DP-02: den Datensatz einer `data.table`-Version laden (Prüfsumme wird kontrolliert)."""
        env = self.get(share_id, version, recipient)
        return dataset_of(env, self.base / _check_id(share_id, "Freigabe"))

    def copy_dataset(self, share_id: str, version: int | None, recipient: str, dest_stem: Path) -> dict:
        """Kopie-Bindung für Datensätze: Werte in den Speicher des Empfängers schreiben; liefert den Umschlag."""
        env = self.get(share_id, version, recipient)
        dataset_of(env, self.base / share_id).save(Path(dest_stem))
        return env


def dataset_of(env: dict, folder: Path):
    """Datensatz aus Umschlag + Nachbardatei."""
    from labdataset import Dataset, DatasetError
    if env.get("kind") != DATA_KIND or not isinstance(env.get("dataset"), dict):
        raise EnvError("Diese Freigabe ist kein Datensatz")
    name = str(env.get("data") or "")
    if not name.endswith(".npz") or "/" in name or "\\" in name or ".." in name:
        raise EnvError("Datensatz: Datei fehlt")
    p = Path(folder) / name
    if not p.exists():
        raise EnvError(f"Datensatz: {name} fehlt")
    import numpy as np
    try:
        with np.load(p, allow_pickle=False) as z:
            data = {k: z[k] for k in z.files}
        ds = Dataset(env["dataset"], data)
    except (DatasetError, ValueError, OSError) as e:
        raise EnvError(f"Datensatz unlesbar: {e}") from e
    if ds.header["data_hash"] != env.get("hash"):
        raise EnvError("Datensatz passt nicht zur Prüfsumme der Freigabe")
    fh = env["dataset"].get("flags_hash")
    if fh and ds.header["flags_hash"] != fh:
        raise EnvError("Markierungen passen nicht zur Prüfsumme der Freigabe")
    return ds
