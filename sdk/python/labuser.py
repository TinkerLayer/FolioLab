"""Eigene Daten eines Moduls (eigene Referenzen, eigene Gleichungen) als JSON-Datei im Ausgabeordner des Moduls.

    store = JsonStore(out_root / "eigene_gleichungen.json", kind="folio-gleichungen/1")
    items = store.items()                 # Liste von dicts, jedes mit "id"
    store.put({"sym": "CI", ...})          # neu (id wird vergeben) oder ersetzen (gleiche id)
    store.delete(id)
    store.export() / store.import_(data, replace=False)

Die Datei ist bewusst lesbar und von Hand editierbar (offen, versionierbar, mit anderen teilbar). Schreiben erfolgt
atomar über eine temporäre Datei; ein Lock schützt gleichzeitige Anfragen.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path


class JsonStore:
    def __init__(self, path: Path, kind: str, max_items: int = 2000):
        self.path = Path(path)
        self.kind = kind
        self.max_items = max_items
        self.lock = threading.RLock()

    def _load(self) -> dict:
        if not self.path.exists():
            return {"format": self.kind, "items": []}
        try:
            d = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise ValueError(f"{self.path.name} ist nicht lesbar: {e}") from e
        if isinstance(d, list):
            d = {"format": self.kind, "items": d}
        d.setdefault("items", [])
        return d

    def _save(self, d: dict):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)

    def items(self) -> list[dict]:
        with self.lock:
            return [dict(x) for x in self._load()["items"] if isinstance(x, dict)]

    def get(self, iid: str) -> dict | None:
        return next((x for x in self.items() if x.get("id") == iid), None)

    def put(self, item: dict) -> dict:
        with self.lock:
            d = self._load()
            item = dict(item)
            item["id"] = str(item.get("id") or uuid.uuid4().hex[:10])
            item["changed"] = time.strftime("%Y-%m-%d %H:%M")
            for i, x in enumerate(d["items"]):
                if x.get("id") == item["id"]:
                    d["items"][i] = item
                    break
            else:
                if len(d["items"]) >= self.max_items:
                    raise ValueError("zu viele Einträge")
                d["items"].append(item)
            self._save(d)
            return item

    def replace_all(self, items: list[dict]):
        with self.lock:
            d = self._load()
            d["items"] = [dict(x, id=str(x.get("id") or uuid.uuid4().hex[:10])) for x in items][: self.max_items]
            self._save(d)

    def delete(self, iid: str) -> bool:
        with self.lock:
            d = self._load()
            n = len(d["items"])
            d["items"] = [x for x in d["items"] if x.get("id") != iid]
            if len(d["items"]) == n:
                return False
            self._save(d)
            return True

    def export(self) -> dict:
        with self.lock:
            return {"format": self.kind, "exported": time.strftime("%Y-%m-%d %H:%M"), "items": self.items()}

    def import_(self, data, replace: bool = False) -> int:
        items = data.get("items") if isinstance(data, dict) else data
        if not isinstance(items, list):
            raise ValueError("Import: Liste von Einträgen erwartet")
        items = [x for x in items if isinstance(x, dict)]
        with self.lock:
            if replace:
                self.replace_all(items)
                return len(items)
            have = {x.get("id") for x in self.items()}
            n = 0
            for x in items:
                x = dict(x)
                if x.get("id") in have:
                    x["id"] = None
                self.put(x)
                n += 1
            return n
