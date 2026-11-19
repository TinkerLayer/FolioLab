"""Röntgendiffraktogramme lesen: Text (xy, csv, txt, dat), PANalytical .xrdml, Bruker .brml und .raw (RAW1.01),
Bruker .uxd, Rigaku .ras.

Ergebnis: Pattern(tth [Grad], counts, meta). meta: name, format, lam1/lam2/ratio (Å) wenn die Datei sie nennt,
anode, step, time, notes (Hinweise des Lesers).

Getestet sind alle Leser mit Dateien, die nach der jeweiligen Formatbeschreibung erzeugt wurden; echte Gerätedateien
lagen nicht vor (methods page).
"""
from __future__ import annotations

import io
import re
import struct
import sys
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

_SDK = Path(__file__).resolve().parents[3] / "sdk" / "python"
if _SDK.is_dir() and str(_SDK) not in sys.path:
    sys.path.insert(0, str(_SDK))

import labtable  # noqa: E402

from .cryst import TUBES  # noqa: E402

EXT = (".xy", ".xye", ".csv", ".txt", ".dat", ".asc", ".xrdml", ".brml", ".raw", ".uxd", ".ras")


class XrdError(ValueError):
    pass


@dataclass
class Pattern:
    tth: np.ndarray
    counts: np.ndarray
    meta: dict = field(default_factory=dict)

    def describe(self) -> dict:
        m = self.meta
        return {"name": m.get("name", ""), "format": m.get("format", ""), "n": int(len(self.tth)),
                "tth_min": float(self.tth[0]), "tth_max": float(self.tth[-1]),
                "step": float(np.median(np.diff(self.tth))) if len(self.tth) > 1 else None,
                "lam1": m.get("lam1"), "lam2": m.get("lam2"), "ratio": m.get("ratio"), "anode": m.get("anode", ""),
                "notes": m.get("notes", [])}


def _finish(tth, y, meta) -> Pattern:
    tth = np.asarray(tth, float)
    y = np.asarray(y, float)
    ok = np.isfinite(tth) & np.isfinite(y)
    tth, y = tth[ok], y[ok]
    if len(tth) < 10:
        raise XrdError("Zu wenige Messpunkte (mindestens 10)")
    o = np.argsort(tth, kind="stable")
    tth, y = tth[o], y[o]
    if tth[0] < -5 or tth[-1] > 180:
        raise XrdError(f"2θ ausserhalb von 0–180° ({tth[0]:.3g} … {tth[-1]:.3g}); ist die erste Spalte der Winkel?")
    if meta.get("anode") and not meta.get("lam1") and meta["anode"] in TUBES:
        l1, l2, r = TUBES[meta["anode"]]
        meta.update(lam1=l1, lam2=l2, ratio=r)
        meta.setdefault("notes", []).append(f"Wellenlänge aus der Anode {meta['anode']} (Standardwerte)")
    return Pattern(tth, y, meta)


# ----------------------------------------------------------------------------- Text
def read_text(data: bytes, name: str) -> Pattern:
    text = labtable.decode(data)
    lines = text.splitlines()
    sn = labtable.sniff(text)
    sep, dec = sn["sep"], sn["dec_comma"]
    start, end, ncol = sn["start"], sn["end"], sn["ncol"]
    if ncol < 2 or end - start < 10:
        raise XrdError("Keine Tabelle mit mindestens zwei Zahlenspalten gefunden")
    rows = []
    for ln in lines[start:end]:
        parts = labtable.split(ln, sep)
        if len(parts) < 2:
            continue
        rows.append([labtable.tofloat(p, dec) for p in parts[:max(2, ncol)]])
    arr = np.array([r[:2] for r in rows], float)
    meta = {"name": name, "format": "Text", "notes": []}
    head = "\n".join(lines[:start])
    m = re.search(r"(?:lambda|wavelength|wellenlänge|kalpha1|k-alpha1|alpha1)\D{0,20}?([0-9]\.[0-9]{3,})", head, re.I)
    if m:
        meta["lam1"] = float(m.group(1))
    for an in TUBES:
        if re.search(rf"\b{an}\b.{{0,6}}(k.?alpha|anode|tube|röhre)|(anode|tube|röhre).{{0,12}}\b{an}\b", head, re.I):
            meta["anode"] = an
            break
    if ncol >= 3:
        meta["notes"].append("Mehr als zwei Spalten: Spalte 1 = 2θ, Spalte 2 = Intensität, weitere ignoriert")
    return _finish(arr[:, 0], arr[:, 1], meta)


# ----------------------------------------------------------------------------- XML-Hilfen
def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _find(el, name):
    for e in el.iter():
        if _local(e.tag) == name:
            return e
    return None


def _findall(el, name):
    return [e for e in el.iter() if _local(e.tag) == name]


def _floats(s: str) -> np.ndarray:
    return np.array([float(x) for x in (s or "").split()], float)


# ----------------------------------------------------------------------------- PANalytical .xrdml
def read_xrdml(data: bytes, name: str) -> Pattern:
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        raise XrdError(f".xrdml ist kein gültiges XML: {e}") from None
    meta = {"name": name, "format": "PANalytical XRDML", "notes": []}
    wl = _find(root, "usedWavelength")
    if wl is not None:
        for tag, key in (("kAlpha1", "lam1"), ("kAlpha2", "lam2"), ("ratioKAlpha2KAlpha1", "ratio")):
            e = _find(wl, tag)
            if e is not None and e.text:
                meta[key] = float(e.text)
    an = _find(root, "anodeMaterial")
    if an is not None and an.text:
        meta["anode"] = an.text.strip()
    scans = _findall(root, "scan")
    if not scans:
        raise XrdError(".xrdml ohne <scan>")
    if len(scans) > 1:
        meta["notes"].append(f"{len(scans)} Scans in der Datei; gelesen wird der erste")
    sc = scans[0]
    dp = _find(sc, "dataPoints")
    if dp is None:
        raise XrdError(".xrdml ohne <dataPoints>")
    pos = None
    for p in _findall(dp, "positions"):
        if p.get("axis") in ("2Theta", "2theta"):
            pos = p
    if pos is None:
        raise XrdError(".xrdml ohne 2θ-Achse (positions axis=\"2Theta\")")
    ints = _find(dp, "intensities")
    unit = "counts"
    if ints is None:
        ints = _find(dp, "counts")
    else:
        unit = ints.get("unit", "counts")
    if ints is None:
        raise XrdError(".xrdml ohne <intensities> oder <counts>")
    y = _floats(ints.text)
    lp = _find(pos, "listPositions")
    if lp is not None and lp.text:
        x = _floats(lp.text)
    else:
        st, en = _find(pos, "startPosition"), _find(pos, "endPosition")
        if st is None or en is None:
            raise XrdError(".xrdml: Anfang/Ende der 2θ-Achse fehlen")
        x = np.linspace(float(st.text), float(en.text), len(y))
    if len(x) != len(y):
        raise XrdError(f".xrdml: {len(x)} Winkel, aber {len(y)} Intensitäten")
    ct = _find(dp, "commonCountingTime")
    if ct is not None and ct.text:
        meta["time"] = float(ct.text)
    if unit == "counts/s" and meta.get("time"):
        meta["notes"].append("Intensität in counts/s (aus der Datei)")
    return _finish(x, y, meta)


# ----------------------------------------------------------------------------- Bruker .brml
def read_brml(data: bytes, name: str) -> Pattern:
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise XrdError(".brml ist kein ZIP-Archiv") from None
    raws = sorted(n for n in z.namelist() if re.search(r"RawData\d*\.xml$", n, re.I))
    if not raws:
        raise XrdError(".brml ohne RawData*.xml")
    meta = {"name": name, "format": "Bruker BRML", "notes": []}
    if len(raws) > 1:
        meta["notes"].append(f"{len(raws)} Messbereiche in der Datei; gelesen wird {raws[0]}")
    root = ET.fromstring(z.read(raws[0]))
    for tag, key in (("WaveLengthAlpha1", "lam1"), ("WaveLengthAlpha2", "lam2"), ("WaveLengthRatio", "ratio")):
        e = _find(root, tag)
        if e is not None and e.get("Value"):
            meta[key] = float(e.get("Value"))
    tube = _find(root, "TubeMaterial")
    if tube is not None and (tube.text or tube.get("Value")):
        meta["anode"] = (tube.text or tube.get("Value")).strip()
    # Datenzeilen: <Datum>Zeit,aktiv,2θ,θ,…,Zählrate</Datum>; welche Spalte 2θ ist, steht in <ScanAxes>/<DataViews>
    # nicht einheitlich; gewählt wird die erste streng steigende Spalte zwischen 0 und 180 (2θ vor θ) und die letzte
    # Spalte als Intensität.
    rows = [[float(v) for v in d.text.split(",")] for d in _findall(root, "Datum") if d.text and "," in d.text]
    if len(rows) < 10:
        raise XrdError(".brml ohne Messpunkte (<Datum>)")
    width = min(len(r) for r in rows)
    A = np.array([r[:width] for r in rows], float)
    cand = [j for j in range(width - 1) if np.all(np.diff(A[:, j]) > 0) and 0 <= A[0, j] < A[-1, j] <= 180]
    if not cand:
        raise XrdError(".brml: keine steigende Winkelspalte gefunden")
    j2 = cand[0]
    if len(cand) >= 2 and np.allclose(A[:, cand[1]] * 2, A[:, cand[0]], rtol=1e-3):
        j2 = cand[0]
    elif len(cand) >= 2 and np.allclose(A[:, cand[0]] * 2, A[:, cand[1]], rtol=1e-3):
        j2 = cand[1]
    meta["notes"].append("Spaltenzuordnung der Datenzeilen erkannt, nicht aus der Datei gelesen (Hinweis Methodenseite)")
    return _finish(A[:, j2], A[:, -1], meta)


# ----------------------------------------------------------------------------- Bruker .raw (Version 3, RAW1.01)
def read_raw(data: bytes, name: str) -> Pattern:
    """Bruker DIFFRAC .raw in der Version RAW1.01 (Aufbau nach der Formatbeschreibung in xylib). Ältere (RAW ) und
    neuere (RAW4.00) Versionen werden abgewiesen."""
    if data[:4] != b"RAW1" or data[4:7] != b".01":
        v = data[:8].decode("latin-1", "replace").strip("\x00 ")
        if v.startswith("RAW4"):
            raise XrdError("Bruker .raw Version 4 (DIFFRAC.SUITE) wird nicht gelesen; bitte als .brml oder .xy "
                           "speichern")
        raise XrdError(f"Bruker .raw Version „{v}“ wird nicht gelesen (nur RAW1.01); bitte als .xy exportieren")
    if len(data) < 712:
        raise XrdError(".raw zu kurz für den Dateikopf")
    meta = {"name": name, "format": "Bruker RAW1.01", "notes": []}
    nrange = struct.unpack_from("<I", data, 12)[0]
    anode = data[608:612].split(b"\x00")[0].decode("latin-1").strip()
    if anode:
        meta["anode"] = anode
    a1, a2 = struct.unpack_from("<dd", data, 624)
    ratio = struct.unpack_from("<d", data, 648)[0]
    if 0.3 < a1 < 3:
        meta["lam1"] = a1
    if 0.3 < a2 < 3:
        meta["lam2"] = a2
    if 0 < ratio < 1:
        meta["ratio"] = ratio
    if not 1 <= nrange <= 100:
        raise XrdError(".raw: unplausible Zahl von Messbereichen")
    off = 712
    xs, ys = [], []
    for r in range(nrange):
        if off + 304 > len(data):
            raise XrdError(".raw: Bereichskopf fehlt")
        hlen, steps = struct.unpack_from("<II", data, off)
        start2th = struct.unpack_from("<d", data, off + 16)[0]
        step = struct.unpack_from("<d", data, off + 176)[0]
        supp = struct.unpack_from("<I", data, off + 256)[0]
        if not (48 < hlen < 10000 and 0 < steps < 10_000_000 and -10 < start2th < 180 and 0 < step < 5 and supp < 1_000_000):
            raise XrdError(".raw: Bereichskopf unplausibel (nur RAW1.01 nach xylib wird gelesen)")
        p = off + hlen + supp
        if p + 4 * steps > len(data):
            raise XrdError(".raw: Messwerte abgeschnitten")
        y = np.frombuffer(data, "<f4", steps, p).astype(float)
        xs.append(start2th + step * np.arange(steps))
        ys.append(y)
        off = p + 4 * steps
        if r == 0:
            meta["step"] = step
    if nrange > 1:
        meta["notes"].append(f"{nrange} Messbereiche aneinandergehängt")
    return _finish(np.concatenate(xs), np.concatenate(ys), meta)


# ----------------------------------------------------------------------------- Bruker .uxd (Text)
def read_uxd(data: bytes, name: str) -> Pattern:
    text = labtable.decode(data)
    meta = {"name": name, "format": "Bruker UXD", "notes": []}
    xs, ys = [], []
    start = step = None
    block_x: list[float] = []
    block_y: list[float] = []

    def flush():
        nonlocal block_x, block_y
        if block_y:
            if block_x and len(block_x) == len(block_y):
                xs.extend(block_x)
            elif start is not None and step is not None:
                xs.extend(start + step * np.arange(len(block_y)))
            else:
                raise XrdError(".uxd: Anfangswinkel oder Schrittweite fehlt")
            ys.extend(block_y)
        block_x, block_y = [], []
    for ln in text.splitlines():
        s = ln.strip()
        if not s or s.startswith(";"):
            continue
        if s.startswith("_"):
            k, _, v = s.partition("=")
            k = k.strip().upper()
            v = v.strip().strip("'\"")
            if k in ("_2THETA", "_START"):
                flush()
                start = float(v)
            elif k == "_STEPSIZE":
                step = float(v)
            elif k in ("_WL1", "_WL"):
                meta["lam1"] = float(v)
            elif k == "_WL2":
                meta["lam2"] = float(v)
            elif k == "_WLRATIO":
                meta["ratio"] = float(v)
            elif k == "_ANODE":
                meta["anode"] = v
            continue
        nums = [float(x) for x in s.replace(",", " ").split()]
        if len(nums) == 2 and start is None:
            block_x.append(nums[0])
            block_y.append(nums[1])
        else:
            block_y.extend(nums)
    flush()
    return _finish(xs, ys, meta)


# ----------------------------------------------------------------------------- Rigaku .ras
def read_ras(data: bytes, name: str) -> Pattern:
    text = data.decode("latin-1")
    meta = {"name": name, "format": "Rigaku RAS", "notes": []}
    if "*RAS_" not in text:
        raise XrdError(".ras ohne *RAS_-Kennungen")
    head = {}
    xs, ys = [], []
    inside = False
    blocks = 0
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith("*RAS_INT_START"):
            inside = True
            blocks += 1
            continue
        if s.startswith("*RAS_INT_END"):
            inside = False
            if blocks == 1:
                continue
        if s.startswith("*"):
            parts = s.split(None, 1)
            if len(parts) == 2:
                head[parts[0][1:].upper()] = parts[1].strip().strip('"')
            continue
        if inside and blocks == 1 and s:
            f = s.split()
            if len(f) >= 2:
                k = float(f[2]) if len(f) >= 3 else 1.0          # Abschwächerfaktor
                xs.append(float(f[0]))
                ys.append(float(f[1]) * k)
    if blocks > 1:
        meta["notes"].append(f"{blocks} Messungen in der Datei; gelesen wird die erste")
    for key, mk in (("HW_XG_WAVE_LENGTH_ALPHA1", "lam1"), ("HW_XG_WAVE_LENGTH_ALPHA2", "lam2")):
        try:
            if head.get(key):
                meta[mk] = float(head[key])
        except ValueError:
            pass
    if head.get("HW_XG_TARGET_NAME"):
        meta["anode"] = head["HW_XG_TARGET_NAME"].strip()
    meta["notes"].append("Intensität = Zählwert × Abschwächerfaktor (dritte Spalte)")
    return _finish(xs, ys, meta)


READERS = {".xrdml": read_xrdml, ".brml": read_brml, ".raw": read_raw, ".uxd": read_uxd, ".ras": read_ras}


def load(data: bytes, name: str) -> Pattern:
    ext = Path(name).suffix.lower()
    if ext in READERS:
        return READERS[ext](data, name)
    if data[:5] == b"<?xml" and b"xrdMeasurement" in data[:4000]:
        return read_xrdml(data, name)
    if data[:4] == b"RAW1":
        return read_raw(data, name)
    if b"*RAS_DATA_START" in data[:200]:
        return read_ras(data, name)
    return read_text(data, name)


def from_columns(tth, counts, name: str, meta: dict | None = None) -> Pattern:
    """Aus einem Datensatz (zwei Spalten)."""
    return _finish(tth, counts, {"name": name, "format": "Datensatz", "notes": [], **(meta or {})})
