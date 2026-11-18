"""Manual sheets – "Einzelmessergebnisse" (DP-M1…M3).

A manual workbook is typed in by hand in the page. It is stored in the environment like a loaded file: one JSON file
(`<name>.messung.json`) with the text of every filled cell as it was typed. Every write gives a new file (new SHA-256),
so a dataset made from it names exactly the state it came from; older states stay while a share version needs them.

    {"format": "folio.messung/1", "rev": 12,
     "sheets": [{"name": "Messung 1", "cells": [[row, col, "12,5"], ...]}]}

Cells are read like a text file with decimal comma or point (`12,5`, `12.5`, `1,2E-3`); other text stays text.
The sheet shown in the page is padded with empty rows and columns so it looks like an empty spreadsheet.
"""
from __future__ import annotations

import json
import re

from .sheet import Builder, ReadError, Sheet

FORMAT = "folio.messung/1"
SUFFIX = ".messung.json"
MAX_SHEETS = 50
MAX_ROWS = 100_000
MAX_COLS = 200
MAX_CELLS = 400_000
MAX_WRITES = 20_000                     # cells per request (pasting a block)
PAD_ROWS, PAD_COLS = 60, 6              # empty space below and right of the used area
MIN_ROWS, MIN_COLS = 100, 26
_NAME = re.compile(r"[\\/:*?\"<>|\x00-\x1f]+")


class ManualError(ValueError):
    pass


def is_manual(fname: str) -> bool:
    return str(fname or "").lower().endswith(SUFFIX)


def clean_name(name: str, default: str = "Messung") -> str:
    return _NAME.sub("_", str(name or "").strip())[:80].strip() or default


class Manual:
    def __init__(self, sheets=None, rev: int = 0):
        self.sheets: list[dict] = sheets or [{"name": "Messung 1", "cells": {}}]
        self.rev = int(rev)

    # ------------------------------------------------------------------ storage
    @classmethod
    def from_bytes(cls, data: bytes) -> "Manual":
        try:
            d = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise ReadError(f"Messtabelle unlesbar: {e}") from e
        if not isinstance(d, dict) or d.get("format") != FORMAT or not isinstance(d.get("sheets"), list):
            raise ReadError("Keine Messtabelle (folio.messung/1)")
        sheets = []
        for s in d["sheets"][:MAX_SHEETS]:
            cells = {}
            for c in (s or {}).get("cells") or []:
                try:
                    r, k, v = int(c[0]), int(c[1]), str(c[2])
                except (TypeError, ValueError, IndexError):
                    continue
                if 0 <= r < MAX_ROWS and 0 <= k < MAX_COLS and v.strip():
                    cells[(r, k)] = v[:2000]
            sheets.append({"name": clean_name((s or {}).get("name"), f"Messung {len(sheets) + 1}"), "cells": cells})
        return cls(sheets or None, d.get("rev") or 0)

    def to_bytes(self) -> bytes:
        return json.dumps({"format": FORMAT, "rev": self.rev,
                           "sheets": [{"name": s["name"], "cells": [[r, c, v] for (r, c), v in sorted(s["cells"].items())]}
                                      for s in self.sheets]},
                          ensure_ascii=False, separators=(",", ":")).encode("utf-8")

    # ------------------------------------------------------------------ editing
    def _sheet(self, k) -> dict:
        try:
            return self.sheets[int(k or 0)]
        except (IndexError, ValueError, TypeError):
            raise ManualError("Blatt nicht gefunden") from None

    def write(self, k, writes) -> list[dict]:
        """Set cells; `writes` = [{r, c, v}] ("" or None empties a cell). Returns the previous values (for undo)."""
        s = self._sheet(k)
        if not isinstance(writes, list) or not writes:
            raise ManualError("Nichts zu schreiben")
        if len(writes) > MAX_WRITES:
            raise ManualError(f"Zu viele Zellen auf einmal (höchstens {MAX_WRITES:,})".replace(",", "'"))
        todo = []
        for w in writes:
            try:
                r, c = int(w["r"]), int(w["c"])
            except (TypeError, ValueError, KeyError):
                raise ManualError("Zelle ungültig") from None
            if not (0 <= r < MAX_ROWS and 0 <= c < MAX_COLS):
                raise ManualError(f"Zelle ausserhalb der Messtabelle (höchstens {MAX_ROWS:,} Zeilen, {MAX_COLS} Spalten)"
                                  .replace(",", "'"))
            v = w.get("v")
            v = "" if v is None else str(v)[:2000]
            todo.append((r, c, v if v.strip() else ""))
        added = sum(1 for r, c, v in todo if v and (r, c) not in s["cells"])
        if len(s["cells"]) + added > MAX_CELLS:
            raise ManualError(f"Messtabelle zu gross (höchstens {MAX_CELLS:,} Zellen)".replace(",", "'"))
        before = []
        for r, c, v in todo:
            before.append({"r": r, "c": c, "v": s["cells"].get((r, c), "")})
            if v:
                s["cells"][(r, c)] = v
            else:
                s["cells"].pop((r, c), None)
        self.rev += 1
        return before

    def add_sheet(self, name: str | None = None) -> int:
        if len(self.sheets) >= MAX_SHEETS:
            raise ManualError(f"Höchstens {MAX_SHEETS} Blätter")
        taken = {s["name"] for s in self.sheets}
        n = len(self.sheets) + 1
        nm = clean_name(name, "")
        base = re.sub(r"\s*\d+$", "", nm) or "Messung"           # "Measurement 3" taken → "Measurement 4"
        while not nm or nm in taken:
            nm, n = f"{base} {n}", n + 1
        self.sheets.append({"name": nm, "cells": {}})
        self.rev += 1
        return len(self.sheets) - 1

    def rename_sheet(self, k, name: str) -> None:
        s = self._sheet(k)
        s["name"] = clean_name(name, s["name"])
        self.rev += 1

    def remove_sheet(self, k) -> None:
        if len(self.sheets) <= 1:
            raise ManualError("Das letzte Blatt bleibt")
        self._sheet(k)
        self.sheets.pop(int(k))
        self.rev += 1

    # ------------------------------------------------------------------ view
    def used(self, k) -> tuple[int, int]:
        cells = self._sheet(k)["cells"]
        if not cells:
            return 0, 0
        return max(r for r, _ in cells) + 1, max(c for _, c in cells) + 1

    def sheet(self, k) -> Sheet:
        """Sheet model for the grid and the recipe; padded with empty space like a fresh spreadsheet."""
        s = self._sheet(k)
        rows, cols = self.used(k)
        b = Builder(s["name"], dec_comma=None, text_numbers=True)
        by_row: dict[int, dict[int, str]] = {}
        for (r, c), v in s["cells"].items():
            by_row.setdefault(r, {})[c] = v
        for r in range(rows):
            row = by_row.get(r)
            if not row:
                b.row(())
                continue
            vals = [None] * (max(row) + 1)
            for c, v in row.items():
                vals[c] = v
            b.row(vals)
        sh = b.sheet()
        from .sheet import NUM, fmt
        for (r, c), v in s["cells"].items():           # numbers are shown as typed ("12,5", "1,2E-3")
            if sh.typ[r, c] == NUM and v.strip() != fmt(float(sh.num[r, c])):
                sh.text[(r, c)] = v.strip()
        R, C = max(rows + PAD_ROWS, MIN_ROWS), max(cols + PAD_COLS, MIN_COLS)
        import numpy as np
        num = np.full((R, C), np.nan)
        typ = np.zeros((R, C), np.uint8)
        num[:sh.rows, :sh.cols] = sh.num
        typ[:sh.rows, :sh.cols] = sh.typ
        return Sheet(s["name"], num, typ, sh.text, [], [], {"manual": True, "used": [rows, cols]})

    def sheets_view(self) -> list[Sheet]:
        return [self.sheet(k) for k in range(len(self.sheets))]


def parse_entry(text: str):
    """One value of the sequential entry: '12,5' → (12.5, ''); '12,5 N' → (12.5, 'N'); 'n.d.' → (None, '')
    (stored as text). Returns (number | None, unit, cell text to store)."""
    import labtable as LT
    from .recipe import _clean_unit, unit_problem, value_unit
    t = str(text or "").strip()
    if not t:
        return None, "", ""
    x = LT.number(t)
    if x is not None:
        return x, "", t
    m = re.match(r"^\s*([-+−]?(?:\d[\d.,']*|[.,]\d+)(?:[eE][-+−]?\d+)?(?:\s*[·×x*]\s*10\^?[-+−]?\d+)?)\s+(\S.*?)\s*$", t)
    if m and LT.number(m.group(1)) is not None:
        u = _clean_unit(m.group(2))
        if not unit_problem(u):
            return LT.number(m.group(1)), u, m.group(1)
    v, u = value_unit(t)
    if v is not None and u and not unit_problem(_clean_unit(u)) and re.match(r"^\s*[-+−\d.,]", t):
        return v, _clean_unit(u), t[:len(t) - len(u)].strip()
    return None, "", t
