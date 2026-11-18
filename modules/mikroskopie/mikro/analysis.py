"""Ein Bild mit seinem Arbeitsstand auswerten: Protokoll anwenden, Auswahlen messen, Partikel analysieren.

Der Arbeitsstand (``state``) kommt aus der Oberflaeche und wird im Bericht als Quelle gespeichert:
  {"pipeline": [...], "slice": 0, "display": {"min", "max", "lut"}, "calib": {"pw", "ph", "unit"} | None,
   "rois": [{..., "name"}], "particles": {params} | None, "region": roi | None,
   "scalebar": false | true | {"len", "pos", "color", "thick", "font", "label", "box"}}
Der Massstabsbalken wird in charts.scalebar_opts gelesen (ältere Stände mit true/false bleiben gültig).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import measure as M
from . import ops
from .imageio import Calib, Stack


@dataclass
class Analysis:
    name: str
    orig: Stack                     # Originalbild (fuer Typ und Quellenangabe)
    proc: ops.Proc
    slice: int
    img: np.ndarray                 # aktuelles 2D-Bild (bzw. H×W×3)
    pre: np.ndarray | None          # Graustufen vor der Schwelle (2D) oder None
    calib: Calib
    state: dict
    measurements: list = field(default_factory=list)
    part: dict | None = None

    @property
    def kind(self) -> str:
        return self.proc.stack.kind

    @property
    def intensity(self) -> np.ndarray:
        """Bild fuer Intensitaetsmessungen: vor der Schwelle, sonst das aktuelle."""
        return self.pre if self.pre is not None else self.img


def run(stack: Stack, state: dict | None, lang: str = "de", with_particles: bool = True) -> Analysis:
    state = state or {}
    proc = ops.apply(stack, state.get("pipeline") or [], lang)
    st = proc.stack
    s = min(max(int(state.get("slice") or 0), 0), st.slices - 1)
    img = st.data[s]
    pre = proc.pre[min(s, proc.pre.shape[0] - 1)] if proc.pre is not None else None
    if pre is not None and pre.shape[:2] != img.shape[:2]:  # nach der Schwelle zugeschnitten/gedreht
        pre = None
    calib = Calib.from_dict(state.get("calib")) if state.get("calib") else st.calib
    if state.get("calib") and sum(1 for p in state.get("pipeline") or [] if p.get("op") == "rotate") % 2:
        # Kalibrierung gilt fuer das Original; nach einer ungeraden Zahl von 90°-Drehungen sind x und y vertauscht
        calib = Calib(calib.ph, calib.pw, calib.unit, calib.square_assumed)
    a = Analysis(name=stack.name, orig=stack, proc=proc, slice=s, img=img, pre=pre, calib=calib, state=state)
    for i, roi in enumerate(state.get("rois") or [], 1):
        roi = roi if roi and roi.get("type") not in (None, "image") else None   # None: ganzes Bild
        row = M.measure(a.intensity, roi, calib)
        row["Label"] = (roi or {}).get("name") or (f"ROI {i}" if roi else "Ganzes Bild")
        a.measurements.append(row)
    if with_particles and state.get("particles") is not None:
        if st.kind != "binary":
            raise ops.OpError("Die Partikelanalyse braucht ein Binärbild. Zuerst Binär ▸ Schwelle anwenden.")
        a.part = M.particles(img > 0, a.intensity, calib, state.get("particles"), state.get("region"))
    return a


def display_for_pre(a: Analysis) -> dict:
    """Anzeigebereich fuer das Bild vor der Schwelle (0,35 % gesaettigt), LUT aus dem Arbeitsstand."""
    v = a.intensity
    if v.ndim == 3:
        return {"min": 0, "max": 255}
    lo, hi = np.nanpercentile(v, [0.175, 99.825])
    return {"min": float(lo), "max": float(hi), "lut": (a.state.get("display") or {}).get("lut", "grays")}
