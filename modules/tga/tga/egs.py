"""TGA-FTIR-Kopplung (TGA-04): Gasspektren-Serien einlesen, Gram-Schmidt-Kurve, Spektrum zu einer Zeit.

Eingaben:
- CSV/TXT-Matrix: erste Zeile = Wellenzahlen (erste Zelle frei oder "t/min"), dann je Zeile Zeit + Absorbanzen;
  oder transponiert (erste Spalte Wellenzahlen, Kopfzeile Zeiten). Zeit in min (Spaltenkopf "s"/"sec" -> s).
- JCAMP-DX mit mehreren Blöcken (je Block ##TITLE, Zeit aus ##$RETENTION TIME, ##$TIME, ##PAGE=T= oder einer Zahl
  im Titel, Daten als ##XYPOINTS=(XY..XY) oder unkomprimiertes ##XYDATA=(X++(Y..Y))). Komprimierte Daten
  (ASDF: SQZ/DIF/DUP) werden gemeldet, nicht geraten.

Gram-Schmidt-Rekonstruktion nach de Haseth & Isenhour (1977): Die ersten k Spektren (Hintergrund vor der Zersetzung)
spannen einen Unterraum auf; die Intensität zur Zeit t ist die Norm des Anteils des Spektrums, der orthogonal zu diesem
Unterraum liegt. Das Verfahren wird hier auf die Absorbanzspektren angewandt (nicht auf Interferogramme).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np

REFS = ["dehaseth1977"]


class EGSError(ValueError):
    pass


@dataclass
class Series:
    name: str
    t: np.ndarray          # min, aufsteigend
    x: np.ndarray          # Wellenzahl 1/cm
    Y: np.ndarray          # (len(t), len(x)) Absorbanz
    meta: dict = field(default_factory=dict)


def _num(s: str) -> float:
    s = s.strip().replace("−", "-")
    if re.fullmatch(r"-?\d+,\d+(?:[eE][-+]?\d+)?", s):
        s = s.replace(",", ".")
    return float(s)


def _isnum(s: str) -> bool:
    try:
        _num(s)
        return True
    except ValueError:
        return False


def _wn_like(v: np.ndarray) -> bool:
    return len(v) >= 10 and np.all((v > 200) & (v < 8000)) and (v.max() - v.min()) > 300


def _sort(t, x, Y, name, meta) -> Series:
    t, x, Y = np.asarray(t, float), np.asarray(x, float), np.asarray(Y, float)
    o = np.argsort(t)
    t, Y = t[o], Y[o]
    ox = np.argsort(x)
    x, Y = x[ox], Y[:, ox]
    if len(t) < 3:
        raise EGSError(f"{name}: zu wenige Spektren ({len(t)}) für eine Zeitreihe")
    if not np.isfinite(Y).any():
        raise EGSError(f"{name}: keine Zahlenwerte")
    return Series(name, t, x, np.nan_to_num(Y), meta)


def parse_matrix(text: str, name: str) -> Series:
    rows = [ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    if len(rows) < 4:
        raise EGSError(f"{name}: zu wenige Zeilen")
    sep = max(";\t,", key=rows[0].count) if any(c in rows[0] for c in ";\t,") else None
    if sep == "," and re.search(r"\d,\d", rows[1]) and ";" not in rows[1] and "\t" not in rows[1] and rows[1].count(",") > rows[0].count(","):
        sep = ","
    split = (lambda s: [c.strip() for c in s.split(sep)]) if sep else (lambda s: s.split())
    head = split(rows[0])
    body = [split(r) for r in rows[1:]]
    n = min(len(head), min(len(b) for b in body))
    head = head[:n]
    if not all(_isnum(h) for h in head[1:]):
        raise EGSError(f"{name}: Kopfzeile muss Wellenzahlen oder Zeiten enthalten")
    hv = np.array([_num(h) for h in head[1:]])
    first = np.array([_num(b[0]) for b in body])
    M = np.array([[_num(c) if _isnum(c) else np.nan for c in b[1:n]] for b in body])
    sec = bool(re.search(r"\b(s|sec|sekunden|seconds)\b", head[0].lower()))
    if _wn_like(hv) and not _wn_like(first):           # Zeilen = Zeiten
        t, x, Y = first, hv, M
    elif _wn_like(first):                              # transponiert: Zeilen = Wellenzahlen
        t, x, Y = hv, first, M.T
    else:
        raise EGSError(f"{name}: keine Wellenzahlachse (400–4000 cm⁻¹) erkannt")
    if sec:
        t = t / 60.0
    return _sort(t, x, Y, name, {"format": "Matrix (CSV/TXT)"})


def _time_of(block: dict) -> float | None:
    for k in ("$RETENTIONTIME", "$TIME", "RETENTIONTIME", "$ELAPSEDTIME"):
        if block.get(k):
            m = re.search(r"-?\d+(?:[.,]\d+)?", block[k])
            if m:
                v = _num(m.group(0))
                return v / 60.0 if re.search(r"\bs(ec)?\b", block[k].lower()) else v
    p = block.get("PAGE", "")
    m = re.search(r"T\s*=\s*(-?\d+(?:[.,]\d+)?)", p)
    if m:
        return _num(m.group(1))
    m = re.search(r"(-?\d+(?:[.,]\d+)?)\s*min", block.get("TITLE", ""))
    if m:
        return _num(m.group(1))
    return None


def _block_xy(b: dict, name: str):
    form = b.get("_form", "").replace(" ", "").upper()
    lines = b.get("_lines", [])
    fx = float(b.get("XFACTOR", "1") or 1)
    fy = float(b.get("YFACTOR", "1") or 1)
    if "XY..XY" in form:
        pts = [p for ln in lines for p in re.split(r"[;\s]+", ln.strip()) if p]
        vals = []
        for p in pts:
            vals += [v for v in p.split(",") if v]
        v = np.array([_num(s) for s in vals])
        return v[0::2] * fx, v[1::2] * fy
    if "X++(Y..Y)" in form:
        xs, ys = [], []
        dx = None
        try:
            fx0, lx, npts = float(b["FIRSTX"]), float(b["LASTX"]), int(float(b["NPOINTS"]))
            dx = (lx - fx0) / (npts - 1)
        except (KeyError, ValueError, ZeroDivisionError):
            pass
        for ln in lines:
            parts = [p for p in re.split(r"[\s,]+", ln.strip()) if p]
            if not all(_isnum(p) for p in parts):         # ASDF (SQZ/DIF/DUP) oder PAC: nicht raten
                raise EGSError(f"{name}: komprimierte JCAMP-Daten (ASDF/PAC) werden für Serien nicht gelesen; "
                               "bitte als CSV-Matrix oder unkomprimiert exportieren")
            x0 = _num(parts[0])
            for i, p in enumerate(parts[1:]):
                xs.append(x0 * fx + (i * dx if dx is not None else 0.0))
                ys.append(_num(p) * fy)
        if dx is None:
            raise EGSError(f"{name}: XYDATA ohne FIRSTX/LASTX/NPOINTS")
        return np.array(xs), np.array(ys)
    raise EGSError(f"{name}: Datenform „{form}“ nicht unterstützt")


def parse_jcamp(text: str, name: str) -> Series:
    blocks, cur, collect = [], None, False
    for raw in text.splitlines():
        line = raw.split("$$")[0].rstrip()
        if line.startswith("##"):
            collect = False
            m = re.match(r"##\s*([^=]*)=\s*(.*)$", line)
            if not m:
                continue
            k = re.sub(r"[\s\-_/]", "", m.group(1)).upper()
            v = m.group(2).strip()
            if k == "TITLE":
                cur = {"TITLE": v}
                blocks.append(cur)
            elif cur is None:
                continue
            elif k in ("XYPOINTS", "XYDATA"):
                cur["_form"], cur["_lines"], collect = v, [], True
            elif k == "END":
                collect = False
            else:
                cur[k] = v
        elif collect and cur is not None and line.strip():
            cur["_lines"].append(line)
    blocks = [b for b in blocks if b.get("_lines")]
    if len(blocks) < 3:
        raise EGSError(f"{name}: JCAMP mit weniger als drei Spektren – keine Zeitreihe")
    ts, specs = [], []
    for i, b in enumerate(blocks):
        tt = _time_of(b)
        if tt is None:
            raise EGSError(f"{name}: Block {i + 1} („{b.get('TITLE', '')}“) ohne Zeitangabe")
        x, y = _block_xy(b, name)
        ts.append(tt)
        specs.append((x, y))
    x0 = np.sort(specs[0][0])
    Y = np.array([np.interp(x0, np.sort(x), y[np.argsort(x)]) for x, y in specs])
    return _sort(ts, x0, Y, name, {"format": "JCAMP-DX (mehrere Blöcke)", "blocks": len(blocks)})


def load_bytes(data: bytes, name: str) -> Series:
    if not data:
        raise EGSError(f"{name}: Datei ist leer")
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if "##TITLE" in text.upper()[:2000] or name.lower().endswith((".jdx", ".dx", ".jcamp")):
        return parse_jcamp(text, name)
    return parse_matrix(text, name)


def gram_schmidt(s: Series, k: int = 5) -> np.ndarray:
    """Gram-Schmidt-Intensität je Spektrum; Basis = erste k Spektren (Hintergrund)."""
    k = int(max(1, min(k, len(s.t) - 2)))
    B = s.Y[:k].T                                      # (nx, k)
    Q, _ = np.linalg.qr(B)
    R = s.Y.T - Q @ (Q.T @ s.Y.T)
    return np.linalg.norm(R, axis=0)


def spectrum_at(s: Series, t: float, k: int = 5, subtract: bool = True) -> dict:
    i = int(np.argmin(np.abs(s.t - float(t))))
    y = s.Y[i].copy()
    if subtract:
        y = y - s.Y[: max(1, min(k, len(s.t) - 2))].mean(axis=0)
    return {"i": i, "t": float(s.t[i]), "x": s.x, "y": y, "subtracted": subtract}


def chemigram(s: Series, lo: float, hi: float) -> np.ndarray:
    """Integrierte Absorbanz im Wellenzahlbereich über der Zeit (z. B. CO2 2250–2400 cm⁻¹)."""
    m = (s.x >= min(lo, hi)) & (s.x <= max(lo, hi))
    if m.sum() < 2:
        raise EGSError("Bereich enthält zu wenige Punkte")
    base = s.Y[:, m]
    f = np.trapezoid if hasattr(np, "trapezoid") else np.trapz
    return f(base, s.x[m], axis=1)


def to_jcamp(x, y, title: str, extra: dict | None = None) -> str:
    """Einzelspektrum als JCAMP-DX (XY..XY) im Format, das das FTIR-Modul liest."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    o = np.argsort(x)[::-1]
    x, y = x[o], y[o]
    lines = [f"##TITLE={title}", "##JCAMP-DX=4.24", "##DATA TYPE=INFRARED SPECTRUM", "##ORIGIN=Folio Lab TGA (Gasanalyse)",
             "##OWNER=", "##XUNITS=1/CM", "##YUNITS=ABSORBANCE"]
    for k, v in (extra or {}).items():
        if v not in (None, ""):
            lines.append(f"##{k}={v}")
    lines += ["##XFACTOR=1", "##YFACTOR=1", f"##FIRSTX={x[0]:.4f}", f"##LASTX={x[-1]:.4f}", f"##NPOINTS={len(x)}",
              f"##FIRSTY={y[0]:.6g}", "##XYPOINTS=(XY..XY)"]
    lines += [f"{a:.4f}, {b:.6g}" for a, b in zip(x, y)]
    lines.append("##END=")
    return "\n".join(lines) + "\n"


def synth(gas_peaks=((20.0, 2.0),), n_t=60, t_end=40.0) -> tuple[bytes, dict]:
    """Synthetische Serie: Hintergrund + CO2-Bande (2350 cm⁻¹), deren Menge als Gauss in der Zeit verläuft."""
    t = np.linspace(0, t_end, n_t)
    x = np.arange(4000.0, 600.0, -4.0)
    bg = 0.02 + 0.00001 * (x - 600) + 0.01 * np.exp(-0.5 * ((x - 1600) / 200) ** 2)
    band = np.exp(-0.5 * ((x - 2350) / 15) ** 2) + 0.4 * np.exp(-0.5 * ((x - 670) / 8) ** 2)
    amt = sum(a * np.exp(-0.5 * ((t - t0) / w) ** 2) for t0, w, a in [(p[0], p[1], 1.0) for p in gas_peaks])
    Y = bg[None, :] + amt[:, None] * band[None, :] * 0.5
    head = "t/min;" + ";".join(f"{v:g}" for v in x)
    rows = [head] + [f"{tt:.4f};" + ";".join(f"{v:.6f}" for v in yy) for tt, yy in zip(t, Y)]
    return ("\n".join(rows) + "\n").encode("utf-8"), {"t_max": float(t[np.argmax(amt)])}
