"""Projekt-Index (A7): kuratierte, projektweite Werte – nur anhängen, nie überschreiben.

Ein Eintrag wird ausdrücklich angelegt („In den Projektindex …“), ist danach unveränderlich und aus jeder Umgebung
jedes Moduls lesbar. Ein abweichender Wert für dieselbe Grösse ist ein *neuer* Eintrag (Alternative) mit eigener ID;
beide bleiben nebeneinander bestehen. Teilen (Sharebox) legt nie etwas im Index ab (Architektur §3, Regel 2).

Ablage:  projects/<pid>/index/<g-id>.json

Eintrag:
    {"schema": "suite.index-entry/1", "id": "g-…", "created": ISO,
     "key": "M(CaCO3)",                      Grösse, unter der Alternativen zusammengefasst werden
     "label": "...", "quantity": {"value", "unit", "u"?},
     "type": measured | calculated | tabulated | estimated,
     "conditions": {...}, "source": {labcite-Datensatz} | None, "note": "...",
     "provenance": {"module", "env", "env_name", "item", "item_name", "share", "version", "module_version"},
     "alternative_to": [g-ids, die es zu dieser Grösse schon gab]}
"""
from __future__ import annotations

import secrets

from labproject import EnvError, Suite, _check_id, _now, _read, _write
from labshare import check_outputs

SCHEMA = "suite.index-entry/1"
TYPES = ("measured", "calculated", "tabulated", "estimated")
TYPE_DE = {"measured": "gemessen", "calculated": "berechnet", "tabulated": "Tabellenwert", "estimated": "Schätzung"}


def _norm_key(k: str) -> str:
    return " ".join(str(k or "").split())[:80]


class ProjectIndex:
    def __init__(self, suite: Suite, project: str | None = None):
        self.suite = suite
        self.project = project

    @property
    def base(self):
        return self.suite.project_dir(self.project) / "index"

    def add(self, key: str, label: str, quantity: dict, type_: str, provenance: dict, conditions=None, source=None,
            note: str = "") -> dict:
        key = _norm_key(key)
        if not key:
            raise EnvError("Grösse (Schlüssel) fehlt")
        if type_ not in TYPES:
            raise EnvError("Art muss gemessen, berechnet, Tabellenwert oder Schätzung sein")
        rec = check_outputs([{"key": key, "label": label, "quantity": quantity, "conditions": conditions or {}}])[0]
        if not (provenance or {}).get("module"):
            raise EnvError("Herkunft (Modul) fehlt")
        if source is not None and not isinstance(source, dict):
            raise EnvError("Quelle muss ein Quellen-Datensatz sein")
        same = [e["id"] for e in self.list(key)]
        eid = "g-" + secrets.token_hex(4)
        path = self.base / f"{eid}.json"
        if path.exists():                                   # praktisch ausgeschlossen; nie überschreiben
            raise EnvError("Eintrag existiert bereits")
        e = {"schema": SCHEMA, "id": eid, "created": _now(), "key": key, "label": rec["label"] or key,
             "quantity": rec["quantity"], "type": type_, "conditions": rec.get("conditions") or {},
             "source": source, "note": str(note or "")[:500],
             "provenance": {k: (provenance or {}).get(k) for k in ("module", "env", "env_name", "item", "item_name",
                                                                   "share", "version", "module_version")},
             "alternative_to": same}
        _write(path, e)
        return e

    def get(self, eid: str) -> dict:
        e = _read(self.base / f"{_check_id(eid, 'Eintrag')}.json")
        if not e:
            raise EnvError("Eintrag nicht gefunden")
        return e

    def list(self, key: str | None = None) -> list[dict]:
        if not self.base.exists():
            return []
        k = _norm_key(key) if key else None
        out = [e for e in (_read(p) for p in self.base.glob("g-*.json")) if isinstance(e, dict)]
        if k:
            out = [e for e in out if e.get("key") == k]
        out.sort(key=lambda e: (e.get("key", ""), e.get("created", ""), len(e.get("alternative_to") or [])))
        return out

    def groups(self) -> list[dict]:
        """Nach Grösse zusammengefasst: [{key, entries:[…]}] – mehrere Einträge = Alternativen."""
        g: dict = {}
        for e in self.list():
            g.setdefault(e["key"], []).append(e)
        return [{"key": k, "entries": v} for k, v in sorted(g.items())]


def route(envs, module: str, module_version: str, action: str, req: dict):
    """Gemeinsame Endpunkte /api/index/{list,add,get} für jeden Modulserver (envs = labproject.ModuleEnvs)."""
    envs.ensure()
    ix = ProjectIndex(envs.suite, envs.project)
    if action == "list":
        return {"groups": ix.groups(), "project": envs.project}
    if action == "get":
        return ix.get(req.get("id") or "")
    if action == "add":
        prov = dict(req.get("provenance") or {})
        env_name = next((e["name"] for e in envs.envs.list() if e["id"] == envs.eid), envs.eid)
        prov.update(module=module, env=envs.eid, env_name=env_name, module_version=module_version)
        return ix.add(req.get("key") or "", req.get("label") or "", req.get("quantity") or {}, req.get("type") or "",
                      prov, req.get("conditions"), req.get("source"), req.get("note") or "")
    raise EnvError("unbekannte Aktion")
