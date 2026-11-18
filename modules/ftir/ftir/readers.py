"""Spektren lesen und schreiben: JCAMP-DX (auch komprimiert und mehrteilig), Thermo OMNIC .spa, GRAMS/Galactic .spc,
Bruker OPUS (opus.py), CSV/TXT (Trennzeichen und Dezimalkomma werden erkannt, mehrere Spalten = mehrere Spektren).

Intern liegen Spektren immer mit aufsteigender Wellenzahl in cm⁻¹ vor; die Darstellung dreht die Achse um.
"""
from __future__ import annotations

import json
import math
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

import labtable as LT

# y-Einheiten: Kürzel -> (deutsch, englisch)
YUNITS = {
    "A": ("Absorbanz", "Absorbance"),
    "T": ("Transmission [%]", "Transmittance [%]"),
    "R": ("Reflexion [%]", "Reflectance [%]"),
    "KM": ("Kubelka-Munk", "Kubelka-Munk"),
    "LR": ("log(1/R)", "log(1/R)"),
    "au": ("Intensität [w. E.]", "Intensity [a.u.]"),
    "D1": ("1. Ableitung", "1st derivative"),
    "D2": ("2. Ableitung", "2nd derivative"),
}


def ylabel(u: str, lang: str = "de") -> str:
    return YUNITS.get(u, YUNITS["au"])[0 if lang == "de" else 1]


class ReadError(ValueError):
    pass


@dataclass
class Spectrum:
    name: str
    x: np.ndarray            # Wellenzahl cm⁻¹, aufsteigend
    y: np.ndarray
    yunit: str = "A"
    meta: dict = field(default_factory=dict)

    def __post_init__(self):
        x = np.asarray(self.x, dtype=float).ravel()
        y = np.asarray(self.y, dtype=float).ravel()
        n = min(len(x), len(y))
        x, y = x[:n], y[:n]
        ok = np.isfinite(x) & np.isfinite(y)
        x, y = x[ok], y[ok]
        o = np.argsort(x, kind="stable")
        x, y = x[o], y[o]
        if len(x) > 1:
            keep = np.concatenate([[True], np.diff(x) > 0])
            x, y = x[keep], y[keep]
        self.x, self.y = x, y

    @property
    def step(self) -> float:
        return float(np.median(np.diff(self.x))) if len(self.x) > 1 else 0.0

    def copy(self, **kw) -> "Spectrum":
        d = dict(name=self.name, x=self.x.copy(), y=self.y.copy(), yunit=self.yunit, meta=dict(self.meta))
        d.update(kw)
        return Spectrum(**d)

    def describe(self) -> dict:
        return {"name": self.name, "n": int(len(self.x)), "xmin": float(self.x[0]), "xmax": float(self.x[-1]),
                "step": round(self.step, 4), "yunit": self.yunit, "meta": self.meta}


def make_uniform(sp: Spectrum) -> Spectrum:
    """Ungleichmässige Abstände (z. B. aus Tabellen) auf ein gleichmässiges Raster bringen; Filter brauchen das."""
    if len(sp.x) < 3:
        return sp
    d = np.diff(sp.x)
    med = float(np.median(d))
    if med <= 0 or np.max(np.abs(d - med)) <= 0.02 * med:
        return sp
    n = int(round((sp.x[-1] - sp.x[0]) / med)) + 1
    xs = np.linspace(sp.x[0], sp.x[-1], n)
    meta = dict(sp.meta, resampled=f"auf {med:.3g} cm⁻¹ gleichmässig interpoliert")
    return sp.copy(x=xs, y=np.interp(xs, sp.x, sp.y), meta=meta)


def _check(sp: Spectrum, name: str) -> Spectrum:
    if len(sp.x) < 10:
        raise ReadError(f"{name}: zu wenige Datenpunkte ({len(sp.x)})")
    if sp.x[0] < 0 or sp.x[-1] > 50000:
        raise ReadError(f"{name}: x-Werte passen nicht zu Wellenzahlen ({sp.x[0]:g} … {sp.x[-1]:g})")
    return make_uniform(sp)


def guess_yunit(y: np.ndarray, hint: str = "") -> tuple[str, np.ndarray]:
    """y-Einheit aus Spaltenname oder Werten: Prozent-Transmission, Transmission als Bruchteil oder Absorbanz."""
    h = (hint or "").lower()
    y = np.asarray(y, dtype=float)
    mx = float(np.nanmax(y)) if y.size else 0.0
    if re.search(r"abs|extinkt|^\s*a\s*$|\(a\)", h):
        return "A", y
    if re.search(r"kubelka|k-?m\b", h):
        return "KM", y
    if re.search(r"refl|%\s*r\b|remission", h):
        return "R", y * 100 if mx <= 1.5 else y
    if re.search(r"%\s*t|trans", h):
        return "T", y * 100 if mx <= 1.5 else y
    med, mn = float(np.nanmedian(y)), float(np.nanmin(y))
    if 20 < med <= 110 and mx <= 130:
        return "T", y
    if 0.5 < med <= 1.05 and mx <= 1.25 and mn >= -0.05 and (mx - med) < 0.5 * (med - mn):
        return "T", y * 100
    return "A", y


def x_to_cm1(x: np.ndarray, unit: str = "") -> np.ndarray:
    u = (unit or "").upper().replace(" ", "")
    x = np.asarray(x, dtype=float)
    if u.startswith("MICRO") or u in ("UM", "µM", "MICRON", "MICRONS"):
        return 1e4 / x
    if u.startswith("NANO") or u == "NM":
        return 1e7 / x
    if not u and len(x) and 0 < np.nanmax(x) <= 50:          # ohne Angabe: Werte bis 50 sind Mikrometer
        return 1e4 / x
    return x


# ----------------------------------------------------------------------------- CSV / TXT
_NUM = re.compile(r"^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$")


def _parse_rows(lines, delim):
    rows, header, pre = [], None, None
    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        parts = s.split(delim) if delim else s.split()
        parts = [p.strip().strip('"').strip("'") for p in parts]
        if delim is None:
            parts = [p for p in parts if p]
        vals, ok = [], True
        for p in parts:
            if p == "":
                vals.append(math.nan)
            elif _NUM.match(p if delim == "," else p.replace(",", ".")) or LT.isnum(p):
                vals.append(LT.tofloat(p, dec_comma=delim != ","))     # DP-01: shared parser (also 1.234,5)
                if math.isnan(vals[-1]):
                    ok = False
                    break
            else:
                ok = False
                break
        if ok and len([v for v in vals if not math.isnan(v)]) >= 2:
            if not rows:
                header = pre
            rows.append(vals)
        elif not rows:
            pre = parts
        elif rows and not ok:
            break                                               # Fusszeilen nach den Daten
    return rows, header


def read_table(text: str, name: str) -> list[Spectrum]:
    lines = text.splitlines()
    best = None
    for delim in (";", "\t", ",", None):
        if delim and not any(delim in ln for ln in lines[:200]):
            continue
        rows, header = _parse_rows(lines, delim)
        if not rows:
            continue
        lens = [len(r) for r in rows]
        width = max(set(lens), key=lens.count)
        good = [r for r in rows if len(r) == width]
        score = len(good) * min(width, 6)
        if best is None or score > best[0]:
            best = (score, good, width, header)
    if best is None or len(best[1]) < 10:
        raise ReadError(f"{name}: keine Zahlenspalten gefunden (erwartet: Wellenzahl und Intensität)")
    _, rows, width, header = best
    a = np.array(rows, dtype=float)
    hdr = list(header or [])
    xunit = hdr[0] if hdr else ""
    x = x_to_cm1(a[:, 0], "MICRO" if re.search(r"µm|um\b|micro|mikro", xunit, re.I) else
                 "NANO" if re.search(r"\bnm\b|nano", xunit, re.I) else "")
    stem = Path(name).stem
    out = []
    for j in range(1, width):
        y = a[:, j]
        if np.isfinite(y).sum() < 10:
            continue
        col = hdr[j] if j < len(hdr) else ""
        unit, yv = guess_yunit(y, col)
        nm = stem if width == 2 else f"{stem} – {col or f'Spalte {j + 1}'}"
        out.append(_check(Spectrum(nm, x, yv, unit, {"format": "CSV/TXT", "column": col or f"{j + 1}"}), name))
    if not out:
        raise ReadError(f"{name}: keine Intensitätsspalte gefunden")
    return out


# ----------------------------------------------------------------------------- JCAMP-DX
_SQZ = {"@": 0, **{c: i + 1 for i, c in enumerate("ABCDEFGHI")}, **{c: -(i + 1) for i, c in enumerate("abcdefghi")}}
_DIF = {"%": 0, **{c: i + 1 for i, c in enumerate("JKLMNOPQR")}, **{c: -(i + 1) for i, c in enumerate("jklmnopqr")}}
_DUP = {**{c: i + 1 for i, c in enumerate("STUVWXYZ")}, "s": 9}


def _asdf_tokens(line: str):
    """Zerlegt eine Datenzeile (AFFN, SQZ, DIF, DUP gemischt) in (Art, Zahlentext)."""
    toks, cur, kind = [], "", None
    i, n = 0, len(line)

    def start(k, s):
        nonlocal cur, kind
        if kind is not None and cur not in ("", "+", "-"):
            toks.append((kind, cur))
        kind, cur = k, s

    while i < n:
        ch = line[i]
        if ch.isdigit() or ch == ".":
            if kind is None:
                kind, cur = "abs", ""
            cur += ch
        elif ch in "Ee" and kind == "abs" and cur and i + 1 < n and (line[i + 1] in "+-"):
            cur += ch + line[i + 1]                                  # Exponent in AFFN (1.2E-03)
            i += 1
        elif ch in "+-":
            start("abs", ch)
        elif ch in _SQZ:
            v = _SQZ[ch]
            start("abs", str(v) if v >= 0 else "-" + str(-v))
        elif ch in _DIF:
            v = _DIF[ch]
            start("dif", str(v) if v >= 0 else "-" + str(-v))
        elif ch in _DUP:
            start("dup", str(_DUP[ch]))
        elif ch == "?":
            start("abs", "nan")
            start(None, "")
        else:
            start(None, "")
        i += 1
    start(None, "")
    return toks


def _asdf_decode(line: str):
    vals, last_kind, last_dif = [], None, 0.0
    for kind, s in _asdf_tokens(line):
        if kind == "abs":
            vals.append(float(s))
            last_kind = "abs"
        elif kind == "dif":
            if not vals:
                raise ReadError("DIF-Wert ohne Ausgangswert")
            last_dif = float(s)
            vals.append(vals[-1] + last_dif)
            last_kind = "dif"
        elif kind == "dup" and vals:
            for _ in range(int(s) - 1):
                vals.append(vals[-1] + last_dif if last_kind == "dif" else vals[-1])
    return vals, last_kind == "dif"


def _key(k: str) -> str:
    return re.sub(r"[\s\-_/]", "", k).upper()


def _jcamp_block(d: dict, fname: str, idx: int) -> Spectrum | None:
    form = d.get("_form", "").replace(" ", "").upper()
    lines = d.get("_lines") or []
    if not lines:
        return None
    f = lambda k, dflt=None: float(d[k]) if k in d and d[k] not in ("", None) else dflt  # noqa: E731
    xf, yf = f("XFACTOR", 1.0), f("YFACTOR", 1.0)
    if "X++" in form:
        ys, prev_dif, x_line0 = [], False, None
        for ln in lines:
            vals, end_dif = _asdf_decode(ln)
            if not vals:
                continue
            if x_line0 is None:
                x_line0 = vals[0]
            yy = vals[1:]
            if prev_dif and yy:
                yy = yy[1:]                                          # Y-Prüfwert der Vorzeile
            ys.extend(yy)
            prev_dif = end_dif
        n = len(ys)
        npts = int(f("NPOINTS", n) or n)
        if 0 < npts < n:
            ys = ys[:npts]
            n = npts
        fx, lx = f("FIRSTX"), f("LASTX")
        if fx is None:
            fx = (x_line0 or 0) * xf
        if lx is None:
            dx = f("DELTAX")
            lx = fx + (dx if dx is not None else 1.0) * (n - 1)
        x = np.linspace(fx, lx, n)
        y = np.array(ys, dtype=float) * yf
    else:                                                            # (XY..XY) oder Peaktabelle
        nums = []
        for ln in lines:
            nums.extend(float(t) for t in re.findall(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?", ln))
        if len(nums) < 20:
            return None
        a = np.array(nums[: len(nums) // 2 * 2]).reshape(-1, 2)
        x, y = a[:, 0] * xf, a[:, 1] * yf
    x = x_to_cm1(x, d.get("XUNITS", "1/CM"))
    yu = d.get("YUNITS", "").upper()
    if "ABSORB" in yu:
        unit, y = "A", y
    elif "TRANSM" in yu:
        unit, y = "T", (y * 100 if np.nanmax(y) <= 1.5 else y)
    elif "KUBELKA" in yu:
        unit = "KM"
    elif "REFLECT" in yu:
        unit, y = "R", (y * 100 if np.nanmax(y) <= 1.5 else y)
    elif "LOG(1/R)" in yu.replace(" ", ""):
        unit = "LR"
    else:
        unit, y = guess_yunit(y, yu)
    meta = {"format": "JCAMP-DX"}
    for k, nm in (("ORIGIN", "origin"), ("OWNER", "owner"), ("DATE", "date"), ("LONGDATE", "date"),
                  ("SPECTROMETERDATASYSTEM", "instrument"), ("SPECTROMETER/DATASYSTEM", "instrument"),
                  ("RESOLUTION", "resolution"), ("CASNAME", "cas_name"), ("CASREGISTRYNO", "cas"),
                  ("MOLFORM", "formula"), ("SAMPLINGPROCEDURE", "sampling"), ("STATE", "state")):
        if d.get(_key(k)):
            meta[nm] = d[_key(k)]
    if d.get(_key(REF_LDR)):
        try:
            refs = json.loads(d[_key(REF_LDR)])
            if isinstance(refs, list):
                meta["refs"] = [r for r in refs if isinstance(r, dict)]
        except ValueError:
            pass
    if d.get(_key(DATASET_LDR)):                                     # DP-13: Spektrum aus einem Datensatz
        try:
            src = json.loads(d[_key(DATASET_LDR)])
            if isinstance(src, dict) and src.get("share"):
                meta["dataset"] = src
        except ValueError:
            pass
    title = d.get("TITLE") or Path(fname).stem
    if idx > 0 and not d.get("TITLE"):
        title += f" ({idx + 1})"
    return _check(Spectrum(title, x, y, unit, meta), fname)


def read_jcamp(text: str, name: str) -> list[Spectrum]:
    out, cur, collecting = [], None, False
    for raw in text.splitlines():
        line = raw.split("$$")[0].rstrip()
        if line.startswith("##"):
            collecting = False
            m = re.match(r"##\s*([^=]*)=\s*(.*)$", line)
            if not m:
                continue
            k, v = _key(m.group(1)), m.group(2).strip()
            if k == "TITLE":
                if cur and cur.get("_lines"):
                    sp = _jcamp_block(cur, name, len(out))
                    if sp:
                        out.append(sp)
                cur = {"TITLE": v}
                continue
            if cur is None:
                cur = {}
            if k in ("XYDATA", "XYPOINTS"):
                cur["_form"], cur["_lines"] = v, []
                collecting = True
                continue
            if k == "END":
                if cur and cur.get("_lines"):
                    sp = _jcamp_block(cur, name, len(out))
                    if sp:
                        out.append(sp)
                cur = None
                continue
            cur[k] = v
        elif collecting and cur is not None and line.strip():
            cur["_lines"].append(line)
    if cur and cur.get("_lines"):
        sp = _jcamp_block(cur, name, len(out))
        if sp:
            out.append(sp)
    if not out:
        raise ReadError(f"{name}: keine Spektrendaten in der JCAMP-Datei")
    return out


REF_LDR = "$FOLIO REF"   # eigenes JCAMP-Feld: Herkunft (Bibliothek, Eintrag, Quelle) enthaltener Referenzspektren
DATASET_LDR = "$FOLIO DATASET"   # DP-13: Herkunft aus einem Datensatz (Freigabe-ID, Titel, Version, Spalten)


def to_jcamp(sp: Spectrum, title: str | None = None, extra: dict | None = None) -> str:
    """JCAMP-DX (XY..XY). Enthält das Spektrum Referenzspektren aus Bibliotheken (meta["refs"]), geht deren Herkunft
    als Feld ##$FOLIO REF mit, damit Bericht und Export sie auch nach Speichern und Wiederöffnen zitieren."""
    yu = {"A": "ABSORBANCE", "T": "TRANSMITTANCE", "R": "REFLECTANCE", "KM": "KUBELKA-MUNK",
          "LR": "LOG(1/R)"}.get(sp.yunit, "ARBITRARY UNITS")
    lines = [f"##TITLE={title or sp.name}", "##JCAMP-DX=4.24", "##DATA TYPE=INFRARED SPECTRUM",
             "##ORIGIN=Folio Lab FTIR", "##OWNER=", "##XUNITS=1/CM", f"##YUNITS={yu}"]
    extra = dict(extra or {})
    if sp.meta.get("refs") and REF_LDR not in extra:
        extra[REF_LDR] = json.dumps(sp.meta["refs"], ensure_ascii=False, separators=(",", ":"))
    for k, v in extra.items():
        if v not in (None, ""):
            lines.append(f"##{k}={v}")
    lines += ["##XFACTOR=1", "##YFACTOR=1", f"##FIRSTX={sp.x[0]:.4f}", f"##LASTX={sp.x[-1]:.4f}",
              f"##NPOINTS={len(sp.x)}", f"##FIRSTY={sp.y[0]:.6g}", "##XYPOINTS=(XY..XY)"]
    lines += [f"{x:.4f}, {y:.6g}" for x, y in zip(sp.x, sp.y)]
    lines.append("##END=")
    return "\n".join(lines) + "\n"


def to_csv(sp: Spectrum, lang: str = "de") -> str:
    head = f"wavenumber_cm-1,{ {'A': 'absorbance', 'T': 'transmittance_percent', 'R': 'reflectance_percent'}.get(sp.yunit, sp.yunit) }"
    return head + "\n" + "\n".join(f"{x:.4f},{y:.7g}" for x, y in zip(sp.x, sp.y)) + "\n"


# ----------------------------------------------------------------------------- Thermo OMNIC .spa
_SPA_Y = {17: "A", 16: "T", 11: "R", 12: "LR", 20: "KM"}


def read_spa(data: bytes, name: str) -> list[Spectrum]:
    if len(data) < 600:
        raise ReadError(f"{name}: zu kurz für eine OMNIC-Datei")
    title = data[30:30 + 256].split(b"\0")[0].decode("latin-1", "replace").strip() or Path(name).stem
    hdr = dat = None
    for k in range(64):                                             # Verzeichnis ab Byte 304, je 16 Byte
        pos = 304 + 16 * k
        if pos + 10 > len(data):
            break
        key = data[pos]
        off, size = struct.unpack_from("<II", data, pos + 2)
        if key == 2 and hdr is None and 0 < off < len(data) - 24:
            hdr = off
        elif key == 3 and dat is None and 0 < off < len(data) and size >= 40 and off + size <= len(data):
            dat = (off, size)
    unit, x = "au", None
    if hdr is not None and dat is not None:
        n = struct.unpack_from("<I", data, hdr + 4)[0]
        ykey = data[hdr + 12]
        fx, lx = struct.unpack_from("<ff", data, hdr + 16)
        nb = dat[1] // 4
        n = nb if not (0 < n <= nb) else n
        y = np.frombuffer(data, "<f4", count=n, offset=dat[0]).astype(float)
        unit = _SPA_Y.get(ykey, "au")
        x = np.linspace(fx, lx, n)
    else:                                                            # ältere Ablage: feste Stellen
        n = struct.unpack_from("<i", data, 564)[0]
        mx, mn = struct.unpack_from("<ff", data, 576)
        pos, flag = 288, 0
        while flag != 3 and pos < 600:
            flag = struct.unpack_from("<H", data, pos)[0]
            pos += 2
        dpos = struct.unpack_from("<H", data, pos)[0]
        if not (0 < n < 10 ** 6) or dpos + 4 * n > len(data):
            raise ReadError(f"{name}: OMNIC-Datei nicht lesbar")
        y = np.frombuffer(data, "<f4", count=n, offset=dpos).astype(float)
        x = np.linspace(mx, mn, n)
    if unit in ("T", "R") and np.nanmax(y) <= 1.5:
        y = y * 100
    if unit == "au":
        unit, y = guess_yunit(y)
    return [_check(Spectrum(title, x, y, unit, {"format": "Thermo OMNIC (.spa)"}), name)]


# ----------------------------------------------------------------------------- GRAMS / Galactic .spc
_SPC_Y = {2: "A", 3: "KM", 128: "T", 129: "R"}


def _spc_meta(data: bytes, name: str) -> dict:
    """Auflösung (fres) und Log-Text (Schlüssel=Wert) einer SPC-Datei. Agilent MicroLab (Cary 630, 4300) speichert
    SPC mit der Endung .fir und schreibt SampleID und die Quelldatei (.a2r) in den Log-Block."""
    meta = {"format": "GRAMS/Galactic (.spc)"}
    res = data[36:45].split(b"\0")[0].decode("latin-1", "replace").strip()
    m = re.match(r"\s*([0-9]+(?:[.,][0-9]+)?)", res)
    if m:
        meta["resolution"] = m.group(1).replace(",", ".")
    log = {}
    try:
        (flogoff,) = struct.unpack_from("<I", data, 248)
        if 512 <= flogoff and flogoff + 64 <= len(data):
            _sizd, _sizm, txto = struct.unpack_from("<III", data, flogoff)
            txt = data[flogoff + txto:].split(b"\0")[0].decode("latin-1", "replace")
            for line in re.split(r"[\r\n]+", txt):
                if "=" in line:
                    k, v = line.split("=", 1)
                    if k.strip():
                        log[k.strip()] = v.strip()
    except struct.error:
        pass
    src = log.get("Spectrum", "")
    if Path(name).suffix.lower() == ".fir" or "MicroLab" in src or src.lower().endswith(".a2r"):
        meta["format"] = "Agilent MicroLab (.fir, SPC)"
        meta["instrument"] = "Agilent MicroLab"
    if log.get("SampleID"):
        meta["sample"] = log["SampleID"]
    if src:
        meta["source"] = re.sub(r"^Exported from\s+", "", src).replace("\\\\", "\\")
    return meta


def read_spc(data: bytes, name: str) -> list[Spectrum]:
    if len(data) < 544:
        raise ReadError(f"{name}: zu kurz für eine SPC-Datei")
    if data[1] != 0x4B:
        raise ReadError(f"{name}: nur das neue SPC-Format (GRAMS ab Version 4) wird unterstützt")
    (ftflgs, _ver, _exper, fexp, fnpts, ffirst, flast, fnsub, fxtype, fytype, _fz, _post, _date) = \
        struct.unpack_from("<BBBbiddiBBBBi", data, 0)
    cmnt = data[88:218].split(b"\0")[0].decode("latin-1", "replace").strip()
    meta = _spc_meta(data, name)
    txvals, txyxys, tmulti, tsprec = ftflgs & 0x80, ftflgs & 0x40, ftflgs & 0x04, ftflgs & 0x01
    off = 512
    xs_common = None
    if txvals and not txyxys:
        xs_common = np.frombuffer(data, "<f4", count=fnpts, offset=off).astype(float)
        off += 4 * fnpts
    out = []
    nsub = max(1, fnsub if tmulti else 1)
    for k in range(nsub):
        if off + 32 > len(data):
            break
        _sf, subexp, _si, _t, _nx, _no, subnpts = struct.unpack_from("<Bbhfffi", data, off)
        off += 32
        n = subnpts if txyxys else fnpts
        if txyxys:
            xs = np.frombuffer(data, "<f4", count=n, offset=off).astype(float)
            off += 4 * n
        else:
            xs = xs_common if xs_common is not None else np.linspace(ffirst, flast, n)
        exp = fexp if fexp == -128 else (subexp if tmulti and subexp != 0 else fexp)
        if exp == -128:
            y = np.frombuffer(data, "<f4", count=n, offset=off).astype(float)
            off += 4 * n
        elif tsprec:
            y = np.frombuffer(data, "<i2", count=n, offset=off).astype(float) * 2.0 ** (exp - 16)
            off += 2 * n
        else:
            y = np.frombuffer(data, "<i4", count=n, offset=off).astype(float) * 2.0 ** (exp - 32)
            off += 4 * n
        xs = x_to_cm1(xs, {2: "MICRO", 3: "NANO"}.get(fxtype, "1/CM"))
        unit = _SPC_Y.get(fytype)
        if unit in ("T", "R") and np.nanmax(y) <= 1.5:
            y = y * 100
        if unit is None:
            unit, y = guess_yunit(y)
        nm = (cmnt or Path(name).stem) + (f" ({k + 1})" if nsub > 1 else "")
        out.append(_check(Spectrum(nm, xs, y, unit, dict(meta)), name))
    if not out:
        raise ReadError(f"{name}: keine Daten in der SPC-Datei")
    return out


# ----------------------------------------------------------------------------- Einstieg
def _text(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1", "replace")


def load_bytes(data: bytes, name: str) -> list[Spectrum]:
    """Alle Spektren einer Datei."""
    ext = Path(name).suffix.lower()
    if data[:4] == b"\x0a\x0a\xfe\xfe":                               # Bruker OPUS, Endung meist .0, .1, …
        from . import opus
        return opus.read(data, name)
    if ext == ".spa":
        return read_spa(data, name)
    if ext in (".spc", ".fir") or (len(data) > 2 and data[1] == 0x4B and data[:1] != b"#"):
        return read_spc(data, name)
    text = _text(data)
    if ext in (".jdx", ".dx", ".jcamp", ".jcm") or text.lstrip().startswith("##"):
        return read_jcamp(text, name)
    if "\0" in text[:2000]:
        raise ReadError(f"{name}: unbekanntes Binärformat (unterstützt: JCAMP-DX, .spa, .spc/.fir, Bruker OPUS, CSV/TXT)")
    return read_table(text, name)
