"""Bilder lesen: TIFF (8/16/32 bit, Stapel, Kalibrierung), PNG, JPEG, BMP, GIF.

Ein Bild ist ein ``Stack``: ``data`` hat die Form (Ebenen, Hoehe, Breite) fuer Graustufen (float32)
oder (Ebenen, Hoehe, Breite, 3) fuer RGB (uint8).
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageSequence

UNITS = {"micron": "µm", "microns": "µm", "um": "µm", "µm": "µm", "\\u00B5m": "µm", "nm": "nm", "nanometer": "nm",
         "mm": "mm", "millimeter": "mm", "cm": "cm", "m": "m", "inch": "in", "pixel": "px", "pixels": "px"}


@dataclass
class Calib:
    """Pixelgroesse. pw (x) und ph (y) getrennt; alle Laengen, Flaechen, Umfaenge, Feret- und Momentgroessen rechnen
    mit beiden. ``square_assumed``: nur eine Pixelgroesse war bekannt, ph = pw wurde angenommen."""
    pw: float = 1.0       # Pixelbreite in unit
    ph: float = 1.0       # Pixelhoehe in unit
    unit: str = "px"
    square_assumed: bool = False

    @property
    def calibrated(self) -> bool:
        return self.unit != "px"

    @property
    def square(self) -> bool:
        return abs(self.pw - self.ph) <= 1e-9 * max(abs(self.pw), abs(self.ph))

    def to_dict(self):
        d = {"pw": self.pw, "ph": self.ph, "unit": self.unit}
        if self.square_assumed:
            d["square_assumed"] = True
        return d

    @staticmethod
    def from_dict(d) -> "Calib":
        if not d:
            return Calib()
        pw = float(d.get("pw") or 1.0)
        assumed = not d.get("ph") or bool(d.get("square_assumed"))
        ph = float(d.get("ph") or pw)
        unit = str(d.get("unit") or "px")
        if pw <= 0 or ph <= 0:
            return Calib()
        return Calib(pw, ph, unit, assumed and abs(pw - ph) <= 1e-9 * pw)


@dataclass
class Stack:
    name: str
    data: np.ndarray            # (S, H, W) float32 oder (S, H, W, 3) uint8
    kind: str                   # "gray" | "rgb" | "binary"
    bitdepth: int               # 8, 16, 32 (gray) bzw. 24 (rgb)
    calib: Calib = field(default_factory=Calib)
    info: dict = field(default_factory=dict)

    @property
    def slices(self) -> int:
        return int(self.data.shape[0])

    @property
    def height(self) -> int:
        return int(self.data.shape[1])

    @property
    def width(self) -> int:
        return int(self.data.shape[2])

    def type_label(self) -> str:
        if self.kind == "rgb":
            return "RGB"
        if self.kind == "binary":
            return "8-bit (binär)"
        return f"{self.bitdepth}-bit"

    def describe(self) -> dict:
        d = self.data
        if self.kind == "rgb":
            mn, mx = 0.0, 255.0
        else:
            mn, mx = float(np.nanmin(d)), float(np.nanmax(d))
        return {"name": self.name, "w": self.width, "h": self.height, "slices": self.slices, "kind": self.kind,
                "bitdepth": self.bitdepth, "type": self.type_label(), "min": mn, "max": mx,
                "calib": self.calib.to_dict(), "info": self.info}


def _frame_array(fr: Image.Image):
    """PIL-Bild -> (array, kind, bitdepth)."""
    mode = fr.mode
    if mode in ("I;16", "I;16L", "I;16B", "I;16N"):
        a = np.array(fr, dtype=np.uint16)
        return a.astype(np.float32), "gray", 16
    if mode == "I":
        a = np.array(fr, dtype=np.int64)
        if a.min() >= 0 and a.max() <= 65535:
            return a.astype(np.float32), "gray", 16
        return a.astype(np.float32), "gray", 32
    if mode == "F":
        return np.array(fr, dtype=np.float32), "gray", 32
    if mode == "1":
        return np.array(fr, dtype=np.float32) * 255.0, "gray", 8
    if mode == "L":
        return np.array(fr, dtype=np.float32), "gray", 8
    if mode == "LA":
        return np.array(fr.convert("L"), dtype=np.float32), "gray", 8
    if mode == "P":
        rgb = np.array(fr.convert("RGB"), dtype=np.uint8)
        if np.array_equal(rgb[..., 0], rgb[..., 1]) and np.array_equal(rgb[..., 1], rgb[..., 2]):
            return rgb[..., 0].astype(np.float32), "gray", 8
        return rgb, "rgb", 24
    rgb = np.array(fr.convert("RGB"), dtype=np.uint8)
    if np.array_equal(rgb[..., 0], rgb[..., 1]) and np.array_equal(rgb[..., 1], rgb[..., 2]):
        return rgb[..., 0].astype(np.float32), "gray", 8
    return rgb, "rgb", 24


# TIFF 6.0, Tag 296 ResolutionUnit: 1 = keine absolute Einheit, 2 = Zoll (Vorgabe, wenn der Tag fehlt), 3 = Zentimeter.
# Umrechnung der Pixelgroesse 1/Resolution in µm.
RES_UNIT_UM = {2: 25400.0, 3: 10000.0}
# Zoll-Aufloesungen, die Kameras, Bildprogramme und Betriebssysteme als Druckvorgabe schreiben. Sie sagen nichts ueber
# die Groesse im Praeparat; 72 dpi ergaebe 352,8 µm/px. Solche Dateien bleiben unkalibriert (wie vor 1.3.0).
PRINT_DPI = {72.0, 96.0, 150.0, 200.0, 240.0, 300.0, 350.0, 400.0, 600.0, 1200.0}


def _pos(v) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    return f if f > 0 and f == f and f != float("inf") else None


def _calibration(im: Image.Image) -> tuple[Calib, str]:
    """Kalibrierung aus TIFF-Tags (XResolution 282, YResolution 283, ResolutionUnit 296, ImageDescription 270).

    1. ImageJ-Beschreibung mit ``unit=…``: Resolution = Pixel je dieser Einheit (ImageJ schreibt dann meist
       ResolutionUnit 1); Pixelbreite 1/XResolution, Pixelhoehe 1/YResolution.
    2. Sonst ResolutionUnit: 2 (Zoll, auch wenn der Tag fehlt) oder 3 (cm) ergibt eine absolute Pixelgroesse, in µm
       umgerechnet; 1 (keine Einheit) ist kein Massstab. Zoll mit einer typischen Druckaufloesung (PRINT_DPI, gleich in
       x und y) ist ebenfalls kein Massstab.
    Fehlt YResolution, wird ph = pw angenommen (``square_assumed``) und die Quelle sagt es."""
    try:
        tags = im.tag_v2 if hasattr(im, "tag_v2") else {}
    except Exception:  # noqa: BLE001
        tags = {}
    desc = str(tags.get(270, "") or "")
    m = re.search(r"(?m)^unit=(.+)$", desc)
    xr, yr = _pos(tags.get(282)), _pos(tags.get(283))
    if not xr:
        return Calib(), ""
    sq = yr is None
    yr = yr or xr
    sq_note = "; nur XResolution vorhanden, quadratische Pixel angenommen" if sq else ""
    if m:
        unit = UNITS.get(m.group(1).strip().lower(), m.group(1).strip())
        if unit == "px":
            return Calib(), ""
        return Calib(1.0 / xr, 1.0 / yr, unit, sq), "Datei (TIFF, unit=…" + sq_note + ")"
    try:
        ru = int(tags.get(296)) if tags.get(296) is not None else 2
    except (TypeError, ValueError):
        ru = 1
    if ru not in RES_UNIT_UM:
        return Calib(), ""
    if ru == 2 and xr == yr and round(xr, 6) in PRINT_DPI:
        return Calib(), ""                                     # Druckvorgabe (72 dpi …), kein Messmassstab
    f = RES_UNIT_UM[ru]
    ytxt = "" if sq or yr == xr else f" × {yr:g}"
    src = (f"Datei (TIFF-Auflösung {xr:g}{ytxt} px/{'cm' if ru == 3 else 'Zoll'}"
           + ("" if tags.get(296) is not None else ", ResolutionUnit fehlt: Zoll nach TIFF 6.0")
           + sq_note
           + ("; Zoll-Auflösungen wie 72/96/300 dpi sind oft nur Druckangaben – bitte prüfen" if ru == 2 else "") + ")")
    return Calib(f / xr, f / yr, "µm", sq), src


def load_bytes(data: bytes, name: str) -> Stack:
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"{name}: kein lesbares Bild (unterstützt: TIFF, PNG, JPEG, BMP, GIF)") from e
    frames, kinds, depths = [], set(), set()
    for fr in ImageSequence.Iterator(im):
        a, k, b = _frame_array(fr)
        frames.append(a)
        kinds.add(k)
        depths.add(b)
        if len(frames) > 2000:
            break
    if not frames:
        raise ValueError(f"{name}: keine Bildebenen")
    if len({f.shape for f in frames}) > 1:
        frames = [f for f in frames if f.shape == frames[0].shape]
    if "rgb" in kinds and len(kinds) > 1:
        frames = [f if f.ndim == 3 else np.repeat(f.astype(np.uint8)[..., None], 3, -1) for f in frames]
        kinds = {"rgb"}
    kind = kinds.pop()
    data_ = np.stack(frames).astype(np.uint8 if kind == "rgb" else np.float32)
    depth = 24 if kind == "rgb" else max(depths)
    calib, src = _calibration(im)
    info = {"format": im.format or "", "mode": im.mode, "calib_source": src, "file_size": len(data)}
    return Stack(name=name, data=data_, kind=kind, bitdepth=depth, calib=calib, info=info)


# ----------------------------------------------------------------------------- Beispielbild
def sample_image(seed: int = 7) -> tuple[bytes, str]:
    """Synthetische Hellfeld-/Fluoreszenzaufnahme mit Partikeln, ungleichmaessigem Hintergrund und
    Rauschen als 16-bit TIFF mit Kalibrierung 0,25 µm/Pixel. Fuer Demo und Tests."""
    rng = np.random.default_rng(seed)
    h, w = 576, 768
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    bg = 900 + 500 * (xx / w) + 300 * np.sin(yy / h * np.pi)
    img = bg.copy()
    for _ in range(70):
        cx, cy = rng.uniform(0, w), rng.uniform(0, h)
        a = rng.uniform(4, 16)
        b = a * rng.uniform(0.55, 1.0)
        th = rng.uniform(0, np.pi)
        c, s = np.cos(th), np.sin(th)
        u = ((xx - cx) * c + (yy - cy) * s) / a
        v = (-(xx - cx) * s + (yy - cy) * c) / b
        r2 = u * u + v * v
        img += rng.uniform(1800, 3200) / (1 + np.exp(np.minimum((r2 - 1) * 9, 60)))
    img += rng.normal(0, 70, img.shape)
    img = np.clip(img, 0, 65535).astype(np.uint16)
    pim = Image.fromarray(img)
    buf = io.BytesIO()
    from PIL.TiffImagePlugin import ImageFileDirectory_v2
    ifd = ImageFileDirectory_v2()
    ifd[270] = "ImageJ=1.54\nunit=micron\nspacing=1\n"
    ifd[282] = 4.0
    ifd[283] = 4.0
    ifd[296] = 1
    pim.save(buf, format="TIFF", tiffinfo=ifd)
    return buf.getvalue(), "Beispiel_Partikel.tif"
