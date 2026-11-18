"""Bruker OPUS (binär, Endungen .0, .1, …) lesen – ohne Zusatzpaket (FT-01).

Aufbau nach der öffentlich dokumentierten Struktur, wie sie freie Leser beschreiben (Bruker selbst veröffentlicht
keine Spezifikation). **Noch nicht mit echten OPUS-Dateien geprüft**, nur mit erzeugten Dateien (siehe `write`).

Datei:  Kopf 24 Byte = Kennung 0A 0A FE FE, Version (float64), Verzeichnis-Offset (int32), max. Blöcke (int32),
        Anzahl Blöcke (int32).
Verzeichnis: je Block 12 Byte = Datentyp (u8), Kanaltyp (u8), Texttyp (u8), frei (u8),
             Länge in 4-Byte-Worten (int32), Offset in Byte (int32).
Datenblock: float32-Werte. Zu jedem Datenblock vom Typ d gehört ein Parameterblock vom Typ d + 16 mit
             NPT (Punkte), FXV/LXV (erstes/letztes x), CSF (y-Faktor), DXU (x-Einheit, WN = cm⁻¹, MI = µm).
Parameterblock: Einträge = Name (3 Zeichen + NUL), Typ (u16: 0 int32, 1 float64, 2–4 Text), Grösse in
             2-Byte-Worten (u16), Wert; Ende mit „END“.

Unbekannte Blöcke werden mit ihren Typ-Kennungen gemeldet (meta["opus_unbekannt"]), nicht gedeutet.
Interferogramme und Phasenspektren werden gemeldet, aber nicht als Spektrum geöffnet.
"""
from __future__ import annotations

import re
import struct
from pathlib import Path

import numpy as np

from .readers import ReadError, Spectrum, _check, guess_yunit

MAGIC = b"\x0a\x0a\xfe\xfe"
NOTE = "nach öffentlicher Formatbeschreibung, noch nicht mit echten OPUS-Dateien geprüft"

# (Datentyp, Kanaltyp) -> Kürzel. Datentyp 7 = Probe, 11 = Referenz, 15 = Ergebnis (AB).
DATA = {(7, 4): "ScSm", (7, 8): "IgSm", (7, 12): "PhSm", (11, 4): "ScRf", (11, 8): "IgRf", (15, 0): "AB"}
SPECTRA = ("AB", "ScSm", "ScRf")                     # werden als Spektrum geöffnet, in dieser Reihenfolge
LABEL = {"AB": "Spektrum (AB)", "ScSm": "Einkanalspektrum Probe", "ScRf": "Einkanalspektrum Referenz",
         "IgSm": "Interferogramm Probe", "IgRf": "Interferogramm Referenz", "PhSm": "Phase Probe"}
# reine Parameterblöcke (Datentyp, 0, 0)
PARAMS = {32: "Instrument", 40: "Instrument (Referenz)", 48: "Probe", 64: "Optik", 96: "Optik (Referenz)"}
_NAME = re.compile(rb"^[A-Z][A-Z0-9]{2}\0$")


def is_opus(data: bytes) -> bool:
    return len(data) >= 24 and data[:4] == MAGIC


def _directory(data: bytes, name: str) -> list[tuple[int, int, int, int, int]]:
    off, _mx, n = struct.unpack_from("<iii", data, 12)
    if not (24 <= off < len(data)) or not (0 < n <= 4096) or off + 12 * n > len(data):
        raise ReadError(f"{name}: OPUS-Verzeichnis unlesbar (Offset {off}, {n} Blöcke)")
    out = []
    for k in range(n):
        dt, ch, tx, _r, ln, bo = struct.unpack_from("<BBBBii", data, off + 12 * k)
        if dt == 0 and ch == 0 and tx == 0 and ln == 0:
            continue                                                  # leerer Eintrag
        if ln < 0 or bo < 0 or bo + 4 * ln > len(data):
            raise ReadError(f"{name}: OPUS-Block {k} zeigt ausserhalb der Datei")
        out.append((dt, ch, tx, ln, bo))
    return out


def params(data: bytes, off: int, words: int, name: str = "") -> dict:
    """Parameterblock -> {Name: Wert}. Ein Eintrag mit ungültigem Namen bricht ab (kein Raten)."""
    end, pos, out = off + 4 * words, off, {}
    while pos + 8 <= end:
        key = data[pos:pos + 4]
        if key[:3] == b"END":
            return out
        if not _NAME.match(key):
            raise ReadError(f"{name}: OPUS-Parameterblock bei Byte {pos} beschädigt")
        typ, size = struct.unpack_from("<HH", data, pos + 4)
        v0, v1 = pos + 8, pos + 8 + 2 * size
        if v1 > end:
            raise ReadError(f"{name}: OPUS-Parameter {key[:3].decode()} zu lang")
        if typ == 0:
            val = struct.unpack_from("<i", data, v0)[0]
        elif typ == 1:
            val = struct.unpack_from("<d", data, v0)[0]
        elif typ in (2, 3, 4):
            val = data[v0:v1].split(b"\0")[0].decode("latin-1").strip()
        else:
            val = None                                                # unbekannter Werttyp: Name bleibt sichtbar
        out[key[:3].decode()] = val
        pos = v1
    return out


def read(data: bytes, name: str) -> list[Spectrum]:
    if not is_opus(data):
        raise ReadError(f"{name}: keine OPUS-Datei (Kennung fehlt)")
    blocks = _directory(data, name)
    data_blocks, par_blocks, other, unknown = {}, {}, {}, []
    for dt, ch, tx, ln, bo in blocks:
        if (dt, ch) in DATA and tx == 0:
            data_blocks[DATA[(dt, ch)]] = (ln, bo)
        elif (dt - 16, ch) in DATA and tx == 0:
            par_blocks[DATA[(dt - 16, ch)]] = params(data, bo, ln, name)
        elif dt in PARAMS and ch == 0 and tx == 0:
            other[PARAMS[dt]] = params(data, bo, ln, name)
        else:
            unknown.append({"datentyp": dt, "kanal": ch, "text": tx, "bytes": 4 * ln})
    info = {}
    for grp in other.values():
        info.update({k: v for k, v in grp.items() if v not in (None, "")})
    title = str(info.get("SNM") or Path(name).stem)
    skipped = [LABEL[k] for k in data_blocks if k not in SPECTRA]
    out, problems = [], []
    for kind in SPECTRA:
        if kind not in data_blocks:
            continue
        p = par_blocks.get(kind)
        if not p or not {"NPT", "FXV", "LXV"} <= p.keys():
            problems.append(f"{LABEL[kind]}: Parameterblock fehlt")
            continue
        ln, bo = data_blocks[kind]
        n = int(p["NPT"])
        if not (10 <= n <= ln):
            problems.append(f"{LABEL[kind]}: NPT = {n} passt nicht zur Blocklänge {ln}")
            continue
        y = np.frombuffer(data, "<f4", count=n, offset=bo).astype(float) * float(p.get("CSF", 1.0) or 1.0)
        x = np.linspace(float(p["FXV"]), float(p["LXV"]), n)
        xu = str(p.get("DXU", "WN")).upper()
        if xu == "MI":
            x = 1e4 / x
        elif xu != "WN":
            problems.append(f"{LABEL[kind]}: x-Einheit {xu} nicht unterstützt")
            continue
        if kind == "AB":
            plf = str(info.get("PLF", "")).upper()
            unit, y = guess_yunit(y, {"AB": "abs", "TR": "trans", "RF": "refl", "KM": "kubelka"}.get(plf, ""))
        else:
            unit = "au"
        meta = {"format": f"Bruker OPUS ({NOTE})", "opus_block": kind}
        for k, lab in (("INS", "instrument"), ("RES", "resolution"), ("NSS", "scans"), ("DAT", "date"),
                       ("TIM", "time"), ("SFM", "sample_form")):
            v = info.get(k, p.get(k))
            if v not in (None, ""):
                meta[lab] = v
        if skipped:
            meta["opus_nicht_geoeffnet"] = skipped
        if unknown:
            meta["opus_unbekannt"] = unknown
        if problems:
            meta["opus_probleme"] = list(problems)
        nm = title if kind == "AB" else f"{title} – {LABEL[kind]}"
        out.append(_check(Spectrum(nm, x, y, unit, meta), name))
    if not out:
        why = "; ".join(problems) or ("nur " + ", ".join(skipped) if skipped else "keine Spektrumsblöcke")
        raise ReadError(f"{name}: OPUS-Datei ohne lesbares Spektrum ({why})")
    return out


# ----------------------------------------------------------------------------- Erzeugen (für Tests)
def _param_block(p: dict) -> bytes:
    b = bytearray()
    for k, v in p.items():
        name = k.encode("ascii")[:3].ljust(3, b" ") + b"\0"
        if isinstance(v, bool) or isinstance(v, int):
            val, typ = struct.pack("<i", int(v)), 0
        elif isinstance(v, float):
            val, typ = struct.pack("<d", v), 1
        else:
            s = str(v).encode("latin-1") + b"\0"
            s += b"\0" * (-len(s) % 4)
            val, typ = s, 2
        b += name + struct.pack("<HH", typ, len(val) // 2) + val
    b += b"END\0" + struct.pack("<HH", 0, 0)
    return bytes(b)


def write(blocks: list[tuple[tuple[int, int, int], bytes]]) -> bytes:
    """Datei aus (Typ-Tripel, Rohbytes) zusammensetzen; Rohbytes werden auf 4 Byte aufgefüllt."""
    n = len(blocks)
    off = 24
    body = bytearray()
    entries = bytearray()
    pos = off + 12 * n
    for (dt, ch, tx), raw in blocks:
        raw = bytes(raw) + b"\0" * (-len(raw) % 4)
        entries += struct.pack("<BBBBii", dt, ch, tx, 0, len(raw) // 4, pos + len(body))
        body += raw
    head = MAGIC + struct.pack("<d", 920622.0) + struct.pack("<iii", off, n, n)
    return head + bytes(entries) + bytes(body)


def write_spectrum(x, y, kind: str = "AB", sample: dict | None = None, extra=(), xunit: str = "WN",
                   csf: float = 1.0) -> bytes:
    """Einfache OPUS-Datei mit einem Spektrum (x absteigend wie bei OPUS), Probenblock und Zusatzblöcken."""
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    dt, ch = next(k for k, v in DATA.items() if v == kind)
    p = {"DPF": 1, "NPT": int(len(x)), "FXV": float(x[0]), "LXV": float(x[-1]), "CSF": float(csf),
         "MXY": float(y.max()), "MNY": float(y.min()), "DXU": xunit, "DAT": "17/11/2026", "TIM": "12:00:00"}
    blocks = [((dt, ch, 0), (y / csf).astype("<f4").tobytes()), ((dt + 16, ch, 0), _param_block(p))]
    if sample:
        blocks.append(((48, 0, 0), _param_block(sample)))
    blocks.extend(extra)
    return write(blocks)
