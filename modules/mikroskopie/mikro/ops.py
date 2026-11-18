"""Bearbeitungsschritte und das reproduzierbare Protokoll (Pipeline).

Eine Pipeline ist eine Liste von Schritten ``{"op": "gauss", "sigma": 2}``. ``apply`` wendet sie auf das
Originalbild an. Weil das Ergebnis nur von Bild und Protokoll abhaengt, kann der Bericht spaeter
exakt neu berechnet werden (Refresh).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from PIL import Image

from . import threshold as T
from .imageio import Calib, Stack
from .label import fill_holes


class OpError(ValueError):
    pass


# ----------------------------------------------------------------------------- Katalog (fuer UI und Bericht)
# type: number | select | bool ; Bedingung "needs": gray | binary | any
OPS: dict[str, dict] = {
    "gray": {"de": "RGB in 8-bit Graustufen", "en": "RGB to 8-bit greyscale", "needs": "rgb",
             "params": [{"key": "weighted", "label": "Gewichtet (0,299 R + 0,587 G + 0,114 B)", "type": "bool", "default": False}]},
    "channel": {"de": "Farbkanal", "en": "Colour channel", "needs": "rgb",
                "params": [{"key": "c", "label": "Kanal", "type": "select", "default": "r",
                            "options": [["r", "Rot"], ["g", "Grün"], ["b", "Blau"]]}]},
    "to8bit": {"de": "In 8-bit umwandeln", "en": "Convert to 8-bit", "needs": "gray", "params": []},
    "invert": {"de": "Invertieren", "en": "Invert", "needs": "any", "params": []},
    "contrast": {"de": "Kontrast verbessern", "en": "Enhance contrast", "needs": "gray",
                 "params": [{"key": "saturated", "label": "Gesättigte Pixel [%]", "type": "number", "default": 0.35,
                             "min": 0, "max": 20, "step": 0.05}]},
    "smooth": {"de": "Glätten (3×3)", "en": "Smooth (3×3)", "needs": "any", "params": []},
    "sharpen": {"de": "Schärfen (3×3)", "en": "Sharpen (3×3)", "needs": "any", "params": []},
    "edges": {"de": "Kanten finden (Sobel)", "en": "Find edges (Sobel)", "needs": "gray", "params": []},
    "gauss": {"de": "Gauss-Filter", "en": "Gaussian blur", "needs": "any",
              "params": [{"key": "sigma", "label": "Sigma [Pixel]", "type": "number", "default": 2, "min": 0.1, "max": 100, "step": 0.1}]},
    "median": {"de": "Medianfilter", "en": "Median filter", "needs": "any",
               "params": [{"key": "r", "label": "Radius [Pixel]", "type": "number", "default": 2, "min": 1, "max": 10, "step": 1}]},
    "mean": {"de": "Mittelwertfilter", "en": "Mean filter", "needs": "any",
             "params": [{"key": "r", "label": "Radius [Pixel]", "type": "number", "default": 2, "min": 1, "max": 50, "step": 1}]},
    "minimum": {"de": "Minimumfilter", "en": "Minimum filter", "needs": "any",
                "params": [{"key": "r", "label": "Radius [Pixel]", "type": "number", "default": 1, "min": 1, "max": 50, "step": 1}]},
    "maximum": {"de": "Maximumfilter", "en": "Maximum filter", "needs": "any",
                "params": [{"key": "r", "label": "Radius [Pixel]", "type": "number", "default": 1, "min": 1, "max": 50, "step": 1}]},
    "unsharp": {"de": "Unscharf maskieren", "en": "Unsharp mask", "needs": "any",
                "params": [{"key": "sigma", "label": "Sigma [Pixel]", "type": "number", "default": 1, "min": 0.1, "max": 50, "step": 0.1},
                           {"key": "weight", "label": "Gewicht (0,1–0,9)", "type": "number", "default": 0.6, "min": 0.1, "max": 0.9, "step": 0.05}]},
    "background": {"de": "Hintergrund abziehen", "en": "Subtract background", "needs": "gray",
                   "params": [{"key": "radius", "label": "Radius [Pixel] (grösser als die Objekte)", "type": "number", "default": 50, "min": 2, "max": 1000, "step": 1},
                              {"key": "light", "label": "Heller Hintergrund", "type": "bool", "default": False}]},
    "math": {"de": "Rechnen", "en": "Math", "needs": "gray",
             "params": [{"key": "fn", "label": "Operation", "type": "select", "default": "mul",
                         "options": [["add", "Addieren"], ["mul", "Multiplizieren"], ["log", "Logarithmus"],
                                     ["sqrt", "Quadratwurzel"], ["gamma", "Gamma"], ["abs", "Betrag"]]},
                        {"key": "v", "label": "Wert", "type": "number", "default": 1, "step": 0.1}]},
    "crop": {"de": "Zuschneiden", "en": "Crop", "needs": "any", "params": []},
    "rotate": {"de": "Drehen um 90°", "en": "Rotate by 90°", "needs": "any",
               "params": [{"key": "dir", "label": "Richtung", "type": "select", "default": "right",
                           "options": [["right", "im Uhrzeigersinn"], ["left", "gegen den Uhrzeigersinn"]]}]},
    "flip": {"de": "Spiegeln", "en": "Flip", "needs": "any",
             "params": [{"key": "axis", "label": "Richtung", "type": "select", "default": "h",
                         "options": [["h", "horizontal"], ["v", "vertikal"]]}]},
    "zproject": {"de": "Z-Projektion", "en": "Z projection", "needs": "any",
                 "params": [{"key": "mode", "label": "Art", "type": "select", "default": "max",
                             "options": [["max", "Maximum"], ["mean", "Mittelwert"], ["sum", "Summe"], ["sd", "Standardabweichung"],
                                         ["min", "Minimum"], ["median", "Median"]]}]},
    "threshold": {"de": "Schwelle (binär machen)", "en": "Threshold (make binary)", "needs": "gray", "params": []},
    "erode": {"de": "Erodieren", "en": "Erode", "needs": "binary",
              "params": [{"key": "n", "label": "Durchgänge", "type": "number", "default": 1, "min": 1, "max": 50, "step": 1}]},
    "dilate": {"de": "Dilatieren", "en": "Dilate", "needs": "binary",
               "params": [{"key": "n", "label": "Durchgänge", "type": "number", "default": 1, "min": 1, "max": 50, "step": 1}]},
    "open": {"de": "Öffnen", "en": "Open", "needs": "binary",
             "params": [{"key": "n", "label": "Durchgänge", "type": "number", "default": 1, "min": 1, "max": 50, "step": 1}]},
    "close": {"de": "Schliessen", "en": "Close", "needs": "binary",
              "params": [{"key": "n", "label": "Durchgänge", "type": "number", "default": 1, "min": 1, "max": 50, "step": 1}]},
    "fill": {"de": "Löcher füllen", "en": "Fill holes", "needs": "binary", "params": []},
    "watershed": {"de": "Wasserscheide (Teilchen trennen)", "en": "Watershed (separate particles)", "needs": "binary",
                  "params": [{"key": "h", "label": "Mindesthöhe h der Maxima [Pixel]", "type": "number", "default": 1.0,
                              "min": 0.1, "max": 50, "step": 0.1}]},
    "outline": {"de": "Umriss", "en": "Outline", "needs": "binary", "params": []},
}


def _f(v, nd, lang):
    s = f"{float(v):.{nd}f}"
    return s.replace(".", ",") if lang == "de" else s


def describe(step: dict, lang: str = "de") -> str:
    """Ein Protokollschritt als Satzteil fuer Protokoll und Methodenteil."""
    op = step.get("op")
    meta = OPS.get(op, {})
    name = meta.get(lang, op)
    de = lang == "de"
    if op == "gauss":
        return f"{name} (σ = {_f(step.get('sigma', 2), 1, lang)} px)"
    if op in ("median", "mean", "minimum", "maximum"):
        return f"{name} (r = {int(step.get('r', 2))} px)"
    if op == "unsharp":
        return f"{name} (σ = {_f(step.get('sigma', 1), 1, lang)} px, {'Gewicht' if de else 'weight'} {_f(step.get('weight', 0.6), 2, lang)})"
    if op == "background":
        light = step.get("light")
        bg = ("heller" if light else "dunkler") if de else ("light" if light else "dark")
        return f"{name} (r = {int(step.get('radius', 50))} px, {bg} {'Hintergrund' if de else 'background'})"
    if op == "contrast":
        return f"{name} ({_f(step.get('saturated', 0.35), 2, lang)} % {'gesättigt' if de else 'saturated'})"
    if op == "to8bit" and step.get("min") is not None:
        return f"{name} ({'Bereich' if de else 'range'} {_f(step['min'], 0, lang)}–{_f(step['max'], 0, lang)})"
    if op == "channel":
        names = {"r": ("Rot", "red"), "g": ("Grün", "green"), "b": ("Blau", "blue")}[step.get("c", "r")]
        return f"{name} {names[0] if de else names[1]}"
    if op == "math":
        fn = step.get("fn", "mul")
        lab = {"add": ("Addieren", "add"), "mul": ("Multiplizieren", "multiply"), "log": ("Logarithmus", "log"),
               "sqrt": ("Quadratwurzel", "square root"), "gamma": ("Gamma", "gamma"), "abs": ("Betrag", "abs")}[fn]
        txt = lab[0] if de else lab[1]
        return f"{txt} ({_f(step.get('v', 1), 2, lang)})" if fn in ("add", "mul", "gamma") else txt
    if op == "crop":
        return f"{name} ({int(step['w'])}×{int(step['h'])} px {'ab' if de else 'at'} {int(step['x'])}, {int(step['y'])})"
    if op == "rotate":
        return f"{name} ({('im Uhrzeigersinn' if de else 'clockwise') if step.get('dir', 'right') == 'right' else ('gegen den Uhrzeigersinn' if de else 'counter-clockwise')})"
    if op == "flip":
        return f"{name} ({'horizontal' if step.get('axis', 'h') == 'h' else 'vertikal' if de else 'vertical'})"
    if op == "zproject":
        return f"{name} ({step.get('mode', 'max')})"
    if op == "threshold":
        method = step.get("method")
        bgtxt = ("dunkler Hintergrund" if step.get("dark", True) else "heller Hintergrund") if de else \
            ("dark background" if step.get("dark", True) else "light background")
        if step.get("lo") is not None and not method:
            return f"{name} ({'manuell' if de else 'manual'} {_f(step['lo'], 1, lang)}–{_f(step['hi'], 1, lang)})"
        return f"{name} ({T.METHODS.get(method or 'default', (method,))[0]}, {bgtxt})"
    if op == "watershed":
        return f"{name} (h = {_f(step.get('h', 1.0), 1, lang)} px)"
    if op in ("erode", "dilate", "open", "close") and int(step.get("n", 1)) > 1:
        return f"{name} ({int(step['n'])}×)"
    if op == "gray" and step.get("weighted"):
        return f"{name} ({'gewichtet' if de else 'weighted'})"
    return name


# ----------------------------------------------------------------------------- Filter (2D float32)
def _conv1d(a: np.ndarray, k: np.ndarray, axis: int) -> np.ndarray:
    r = len(k) // 2
    pad = [(r, r) if ax == axis else (0, 0) for ax in range(2)]
    p = np.pad(a, pad, mode="edge")
    out = np.zeros(a.shape, dtype=np.float32)
    n = a.shape[axis]
    for i, w in enumerate(k):
        sl = [slice(None), slice(None)]
        sl[axis] = slice(i, i + n)
        out += np.float32(w) * p[tuple(sl)]
    return out


def gauss(a: np.ndarray, sigma: float) -> np.ndarray:
    sigma = float(sigma)
    if sigma <= 0:
        return a.copy()
    r = max(1, int(math.ceil(3.0 * sigma)))
    x = np.arange(-r, r + 1, dtype=np.float64)
    k = np.exp(-0.5 * (x / sigma) ** 2)
    k /= k.sum()
    return _conv1d(_conv1d(a, k, 0), k, 1)


def box_mean(a: np.ndarray, r: int) -> np.ndarray:
    r = int(r)
    k = 2 * r + 1
    p = np.pad(a.astype(np.float64), r, mode="edge")
    c = np.zeros((p.shape[0] + 1, p.shape[1] + 1))
    c[1:, 1:] = p.cumsum(0).cumsum(1)
    s = c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]
    return (s / (k * k)).astype(np.float32)


def _minmax(a: np.ndarray, r: int, fn) -> np.ndarray:
    r = int(r)
    if r < 1:
        return a.copy()
    k = 2 * r + 1
    p = np.pad(a, ((0, 0), (r, r)), mode="edge")
    t = fn(sliding_window_view(p, k, axis=1), axis=-1)
    p = np.pad(t, ((r, r), (0, 0)), mode="edge")
    return fn(sliding_window_view(p, k, axis=0), axis=-1).astype(np.float32)


def min_filter(a, r):
    return _minmax(a, r, np.min)


def max_filter(a, r):
    return _minmax(a, r, np.max)


def median(a: np.ndarray, r: int) -> np.ndarray:
    r = int(r)
    k = 2 * r + 1
    p = np.pad(a, r, mode="edge")
    out = np.empty(a.shape, dtype=np.float32)
    blk = max(8, int(4_000_000 // max(1, a.shape[1] * k * k)))
    for y0 in range(0, a.shape[0], blk):
        y1 = min(a.shape[0], y0 + blk)
        win = sliding_window_view(p[y0:y1 + 2 * r], (k, k))
        out[y0:y1] = np.median(win.reshape(win.shape[0], win.shape[1], -1), axis=-1)
    return out


def _conv3(a: np.ndarray, kern) -> np.ndarray:
    p = np.pad(a, 1, mode="edge")
    H, W = a.shape
    out = np.zeros((H, W), dtype=np.float32)
    for dy in range(3):
        for dx in range(3):
            w = kern[dy][dx]
            if w:
                out += np.float32(w) * p[dy:dy + H, dx:dx + W]
    return out


def sobel(a: np.ndarray) -> np.ndarray:
    gx = _conv3(a, [[-1, 0, 1], [-2, 0, 2], [-1, 0, 1]])
    gy = _conv3(a, [[-1, -2, -1], [0, 0, 0], [1, 2, 1]])
    return np.sqrt(gx * gx + gy * gy)


def background(a: np.ndarray, radius: float, light: bool, maxv: float) -> np.ndarray:
    """Hintergrund als grauwertmorphologische Oeffnung (Minimum, dann Maximum) mit Radius r schaetzen und
    abziehen. Fuer Geschwindigkeit auf einem verkleinerten Bild gerechnet und bilinear vergroessert."""
    b = (maxv - a) if light else a
    H, W = b.shape
    shrink = max(1, int(radius // 10))
    if shrink > 1:
        hh, ww = (H // shrink) * shrink, (W // shrink) * shrink
        small = b[:hh, :ww].reshape(hh // shrink, shrink, ww // shrink, shrink).min(axis=(1, 3))
    else:
        small = b
    rs = max(1, int(round(radius / shrink)))
    bg = max_filter(min_filter(small, rs), rs)
    if shrink > 1:
        bg = np.asarray(Image.fromarray(bg.astype(np.float32), mode="F").resize((W, H), Image.BILINEAR), dtype=np.float32)
    bg = box_mean(bg, max(1, shrink // 2))
    res = np.maximum(b - np.minimum(bg, b), 0)
    return (maxv - res) if light else res


# ----------------------------------------------------------------------------- Binaer
def _erode(m: np.ndarray, n: int) -> np.ndarray:
    for _ in range(int(n)):
        m = _minmax(m.astype(np.float32), 1, np.min) > 0
    return m


def _dilate(m: np.ndarray, n: int) -> np.ndarray:
    for _ in range(int(n)):
        m = _minmax(m.astype(np.float32), 1, np.max) > 0
    return m


# ----------------------------------------------------------------------------- Pipeline
@dataclass
class Proc:
    stack: Stack                       # Ergebnis
    pre: np.ndarray | None = None      # Graustufen unmittelbar vor der (ersten) Schwelle, (S, H, W)
    thr: dict | None = None            # Angaben zur Schwelle
    steps: list = field(default_factory=list)


def _maxval(bitdepth: int, data: np.ndarray) -> float:
    if bitdepth == 8:
        return 255.0
    if bitdepth == 16:
        return 65535.0
    return float(np.nanmax(data)) if data.size else 1.0


def _per_channel(fn, data: np.ndarray, kind: str) -> np.ndarray:
    """fn(2D float) auf jede Ebene (und bei RGB auf jeden Kanal) anwenden."""
    if kind == "rgb":
        out = np.empty_like(data)
        for s in range(data.shape[0]):
            for c in range(3):
                out[s, ..., c] = np.clip(np.round(fn(data[s, ..., c].astype(np.float32))), 0, 255).astype(np.uint8)
        return out
    return np.stack([fn(data[s]).astype(np.float32) for s in range(data.shape[0])])


def _clamp(d: np.ndarray, bitdepth: int) -> np.ndarray:
    if bitdepth == 8:
        return np.clip(np.round(d), 0, 255).astype(np.float32)
    if bitdepth == 16:
        return np.clip(np.round(d), 0, 65535).astype(np.float32)
    return d.astype(np.float32)


def apply_step(st: Stack, step: dict, proc: Proc) -> Stack:
    op = step.get("op")
    meta = OPS.get(op)
    if meta is None:
        raise OpError(f"Unbekannter Schritt: {op}")
    need = meta["needs"]
    if need == "gray" and st.kind == "rgb":
        raise OpError(f"„{meta['de']}“ geht nur mit Graustufenbildern. Zuerst Bild ▸ Typ ▸ 8-bit.")
    if need == "rgb" and st.kind != "rgb":
        raise OpError(f"„{meta['de']}“ geht nur mit RGB-Bildern.")
    if need == "binary" and st.kind != "binary":
        raise OpError(f"„{meta['de']}“ geht nur mit Binärbildern. Zuerst Binär ▸ Schwelle anwenden.")
    d, kind, bd = st.data, st.kind, st.bitdepth
    mv = _maxval(bd, d) if kind != "rgb" else 255.0

    if op == "gray":
        f = d.astype(np.float32)
        g = f @ np.array([0.299, 0.587, 0.114], np.float32) if step.get("weighted") else f.mean(axis=-1)
        return replace(st, data=np.round(g).astype(np.float32), kind="gray", bitdepth=8)
    if op == "channel":
        c = {"r": 0, "g": 1, "b": 2}[step.get("c", "r")]
        return replace(st, data=d[..., c].astype(np.float32), kind="gray", bitdepth=8)
    if op == "to8bit":
        lo = float(step["min"]) if step.get("min") is not None else float(np.nanmin(d))
        hi = float(step["max"]) if step.get("max") is not None else float(np.nanmax(d))
        if hi <= lo:
            hi = lo + 1
        out = np.clip(np.round((d - lo) / (hi - lo) * 255.0), 0, 255).astype(np.float32)
        return replace(st, data=out, kind="binary" if kind == "binary" else "gray", bitdepth=8)
    if op == "invert":
        if kind == "rgb":
            return replace(st, data=(255 - d).astype(np.uint8))
        if kind == "binary":
            return replace(st, data=(255.0 - d).astype(np.float32))
        if bd == 32:
            return replace(st, data=(float(np.nanmin(d)) + float(np.nanmax(d)) - d).astype(np.float32))
        return replace(st, data=(mv - d).astype(np.float32))
    if op == "contrast":
        sat = float(step.get("saturated", 0.35)) / 100.0
        lo, hi = np.nanpercentile(d, [sat / 2 * 100, 100 - sat / 2 * 100])
        if hi <= lo:
            return st
        top = 1.0 if bd == 32 else mv
        out = np.clip((d - lo) / (hi - lo) * top, 0, top)
        return replace(st, data=_clamp(out, bd))
    if op in ("smooth", "sharpen", "gauss", "median", "mean", "minimum", "maximum", "unsharp"):
        if kind == "binary" and op not in ("minimum", "maximum", "median"):
            kind = "gray"
        if op == "smooth":
            fn = lambda a: box_mean(a, 1)  # noqa: E731
        elif op == "sharpen":
            fn = lambda a: _conv3(a, [[-1, -1, -1], [-1, 12, -1], [-1, -1, -1]]) / 4.0  # noqa: E731
        elif op == "gauss":
            fn = lambda a: gauss(a, float(step.get("sigma", 2)))  # noqa: E731
        elif op == "median":
            fn = lambda a: median(a, int(step.get("r", 2)))  # noqa: E731
        elif op == "mean":
            fn = lambda a: box_mean(a, int(step.get("r", 2)))  # noqa: E731
        elif op == "minimum":
            fn = lambda a: min_filter(a, int(step.get("r", 1)))  # noqa: E731
        elif op == "maximum":
            fn = lambda a: max_filter(a, int(step.get("r", 1)))  # noqa: E731
        else:
            s, w = float(step.get("sigma", 1)), float(step.get("weight", 0.6))
            w = min(max(w, 0.1), 0.9)
            fn = lambda a: (a - w * gauss(a, s)) / (1 - w)  # noqa: E731
        out = _per_channel(fn, d, st.kind)
        if st.kind != "rgb":
            out = _clamp(out, bd)
        return replace(st, data=out, kind=kind)
    if op == "edges":
        return replace(st, data=_clamp(_per_channel(sobel, d, kind), bd), kind="gray")
    if op == "background":
        r, light = float(step.get("radius", 50)), bool(step.get("light"))
        top = mv if bd != 32 else float(np.nanmax(d))
        return replace(st, data=_clamp(_per_channel(lambda a: background(a, r, light, top), d, kind), bd))
    if op == "math":
        fn, v = step.get("fn", "mul"), float(step.get("v", 1))
        with np.errstate(divide="ignore", invalid="ignore"):
            if fn == "add":
                return replace(st, data=_clamp(d + v, bd))
            if fn == "mul":
                return replace(st, data=_clamp(d * v, bd))
            if fn == "abs":
                return replace(st, data=np.abs(d).astype(np.float32))
            if fn == "gamma":
                top = mv if bd != 32 else max(float(np.nanmax(d)), 1e-12)
                return replace(st, data=_clamp(np.power(np.clip(d / top, 0, None), v) * top, bd))
            if fn == "log":
                out = np.log(np.maximum(d, 0) + (1.0 if bd != 32 else 0.0))
            else:
                out = np.sqrt(np.maximum(d, 0))
        out[~np.isfinite(out)] = 0
        return replace(st, data=out.astype(np.float32), kind="gray", bitdepth=32)
    if op == "crop":
        x, y = max(0, int(step.get("x", 0))), max(0, int(step.get("y", 0)))
        w, h = int(step.get("w", st.width)), int(step.get("h", st.height))
        x2, y2 = min(st.width, x + w), min(st.height, y + h)
        if x2 - x < 1 or y2 - y < 1:
            raise OpError("Die Auswahl liegt ausserhalb des Bildes.")
        return replace(st, data=d[:, y:y2, x:x2].copy())
    if op == "rotate":
        k = -1 if step.get("dir", "right") == "right" else 1
        cal = Calib(st.calib.ph, st.calib.pw, st.calib.unit)
        return replace(st, data=np.ascontiguousarray(np.rot90(d, k=k, axes=(1, 2))), calib=cal)
    if op == "flip":
        ax = 2 if step.get("axis", "h") == "h" else 1
        return replace(st, data=np.ascontiguousarray(np.flip(d, axis=ax)))
    if op == "zproject":
        mode = step.get("mode", "max")
        f = d.astype(np.float32)
        out = {"max": np.max, "min": np.min, "mean": np.mean, "sum": np.sum, "sd": np.std, "median": np.median}[mode](f, axis=0)
        if kind == "rgb":
            return replace(st, data=np.clip(np.round(out), 0, 255).astype(np.uint8)[None])
        nbd = bd if mode in ("max", "min", "median") else 32
        return replace(st, data=out[None].astype(np.float32), bitdepth=nbd,
                       kind="binary" if kind == "binary" and mode in ("max", "min") else "gray")
    if op == "threshold":
        if kind == "binary":
            return st
        if proc.pre is None:
            proc.pre = d.copy()
        method = step.get("method")
        dark = bool(step.get("dark", True))
        out = np.empty_like(d, dtype=np.float32)
        info = None
        for s in range(d.shape[0]):
            if step.get("lo") is not None and step.get("hi") is not None and not method:
                lo, hi = float(step["lo"]), float(step["hi"])
                info = {"method": None, "lo": lo, "hi": hi, "dark": dark}
            else:
                src = d if step.get("stack") else d[s]
                info = T.auto_range(src, bd, method or "default", dark)
                info["dark"] = dark
                lo, hi = info["lo"], info["hi"]
            out[s] = np.where((d[s] >= lo) & (d[s] <= hi), 255.0, 0.0)
        proc.thr = info
        return replace(st, data=out, kind="binary", bitdepth=8)
    # binaer
    m = d > 0
    n = int(step.get("n", 1))
    res = []
    for s in range(m.shape[0]):
        x = m[s]
        if op == "erode":
            x = _erode(x, n)
        elif op == "dilate":
            x = _dilate(x, n)
        elif op == "open":
            x = _dilate(_erode(x, n), n)
        elif op == "close":
            x = _erode(_dilate(x, n), n)
        elif op == "fill":
            x = fill_holes(x)
        elif op == "watershed":
            from .watershed import watershed
            x, _info = watershed(x, float(step.get("h", 1.0)))
        elif op == "outline":
            x = x & ~_erode(x, 1)
        res.append(x)
    return replace(st, data=np.stack(res).astype(np.float32) * 255.0)


def apply(original: Stack, pipeline: list[dict], lang: str = "de") -> Proc:
    st = original
    proc = Proc(stack=st)
    for i, step in enumerate(pipeline or []):
        try:
            st = apply_step(st, step, proc)
        except OpError as e:
            raise OpError(f"Schritt {i + 1} ({describe(step, 'de')}): {e}") from e
        proc.steps.append(describe(step, lang))
    proc.stack = st
    return proc
