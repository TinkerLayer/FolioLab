"""Messunsicherheit der FTIR-Ergebnisse: Bandenlagen, Peaklagen, Bandenflächen und -höhen, Verhältnisse und eigene
Gleichungen mit A(ν), y(ν), area(ν1, ν2), area0(ν1, ν2), height(ν1, ν2).

Arbeitsstand::

    state["unc"] = {"nu": {"parts": [...]}, "noise": {"parts": [...]}}   wie LabUnc.all()
        nu     Genauigkeit der Wellenzahlachse (cm⁻¹; Gerätespezifikation, eigenes Messmittel oder Vorlage PRESETS)
        noise  Rauschen je Punkt von Hand (in der Einheit der Flächenrechnung, Absorbanz bzw. log(1/R))
    state["unc_noise"] = {"mode": "off"|"auto"|"region"|"manual", "region": [hoch, tief]}
        auto    σ je Punkt aus quality.effective_noise (Rest einer Savitzky-Golay-Glättung, wie das S/N)
        region  RMS der Punkte eines rauschfreien Bereichs nach Abzug einer Geraden, Typ A, n − 2 Freiheitsgrade
        manual  state["unc"]["noise"]
    state["unc_method"] = {"method", "p", "k"}

Ansatz: Jede rauschabhängige Grösse ist eine lineare Funktion der Messwerte, Q = Σ cᵢ yᵢ (Trapezfläche über einer
Geraden durch die Grenzpunkte, Höhe über dieser Geraden, Interpolation für A(ν)); die Peaklage (Parabel durch drei
Punkte) wird linearisiert. Damit ist u²(Q) = Σ cᵢ² σᵢ² und die Kovarianz zweier Grössen Σ cᵢ c'ᵢ σᵢ² exakt bekannt –
überlappende Banden in Verhältnissen und Gleichungen bleiben richtig korreliert. Dazu kommen gemeinsame Quellen
(Achsenfehler δν̃ für alle Lagen und, über die Steigung, für A(ν)) und je Bande eine Typ-B-Angabe für die Wahl der
Grenzen (halbe Spannweite der Fläche bei Grenzen ±1 Punkt, Rechteck) sowie die Interpolation zwischen Messpunkten
(Punktabstand, Rechteck). Die Fortpflanzung macht ``labcalc.uncertainty`` (GUM, JCGM 100:2008; GUM S1, JCGM 101:2008).
"""
from __future__ import annotations

import math
import re

import numpy as np

try:
    from labcalc import uncertainty as UN
except ImportError:  # Modul ausserhalb von Folio Lab
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "sdk" / "python"))
    from labcalc import uncertainty as UN

from . import peaks as PK
from . import quality as QA

KEYS = ("nu", "noise")
UNCHECKED = "Angaben nicht am Original geprüft"

# Modul-eigene Quellen (labcite-Einträge), soweit nicht in der gemeinsamen Bibliothek
SOURCES = {
    "ph-eur-2-2-24": {"type": "standard", "title": "Europäisches Arzneibuch, 2.2.24 Absorptionsspektroskopie im Infrarot "
                      "(Prüfung der Wellenzahlskala mit Polystyrol)",
                      "container": "European Directorate for the Quality of Medicines & HealthCare (EDQM)",
                      "note": UNCHECKED},
    "astm-e1421": {"type": "standard", "title": "ASTM E1421 Standard Practice for Describing and Measuring Performance of "
                   "Fourier Transform Mid-Infrared (FT-MIR) Spectrometers: Level Zero and Level One Tests",
                   "container": "ASTM International", "note": UNCHECKED},
    "savitzky1964": {"type": "article", "authors": "Savitzky, Abraham; Golay, Marcel J. E.",
                     "title": "Smoothing and Differentiation of Data by Simplified Least Squares Procedures",
                     "container": "Analytical Chemistry", "year": "1964", "volume": "36", "issue": "8",
                     "pages": "1627-1639"},
}

# Vorlagen für die Wellenzahlgenauigkeit (Seite: Knopf neben dem ±)
PRESETS = {
    "pheur": {"label": {"de": "Ph. Eur. 2.2.24: ±1,0 cm⁻¹ (Polystyrol 1601,2 cm⁻¹)",
                        "en": "Ph. Eur. 2.2.24: ±1.0 cm⁻¹ (polystyrene 1601.2 cm⁻¹)"},
              "spec": {"parts": [{"kind": "limits", "a": 1.0, "dist": "rect",
                                  "label": "Ph. Eur. 2.2.24, Toleranz der Polystyrolbande 1601,2 cm⁻¹ (" + UNCHECKED + ")",
                                  "source": SOURCES["ph-eur-2-2-24"]}]}},
}

L10N = {
    "de": {"noise": "Rauschen", "noise_auto": "Rauschen (Typ A, automatisch aus dem Glättungsrest, σ₀ = {s})",
           "noise_reg": "Rauschen (Typ A, RMS im Bereich {hi}–{lo} cm⁻¹ nach Geradenabzug, n = {n}, σ = {s})",
           "noise_man": "Rauschen (Angabe, σ = {s})", "nu": "Wellenzahlgenauigkeit δν̃",
           "base": "Grenzen/Basislinie ({w}, ±1 Punkt)", "interp": "Peak-Interpolation (Punktabstand {d} cm⁻¹)",
           "area": "Fläche {n}", "height": "Höhe {n}", "pos": "Lage {n}", "peak": "Bande {x} cm⁻¹", "ratio": "Verhältnis {n}",
           "region_bad": "Rauschbereich {hi}–{lo} cm⁻¹ hat zu wenige Punkte (mindestens 5).",
           "bad": "{k}: {e}", "call": "{f}({a})", "deriv": "Rauschen auf einer Ableitung: Einheit der Ableitung."},
    "en": {"noise": "Noise", "noise_auto": "Noise (type A, automatic from the smoothing residual, σ₀ = {s})",
           "noise_reg": "Noise (type A, RMS in {hi}–{lo} cm⁻¹ after removing a line, n = {n}, σ = {s})",
           "noise_man": "Noise (stated, σ = {s})", "nu": "Wavenumber accuracy δν̃",
           "base": "Limits/baseline ({w}, ±1 point)", "interp": "Peak interpolation (point spacing {d} cm⁻¹)",
           "area": "Area {n}", "height": "Height {n}", "pos": "Position {n}", "peak": "Band {x} cm⁻¹", "ratio": "Ratio {n}",
           "region_bad": "Noise region {hi}–{lo} cm⁻¹ has too few points (at least 5).",
           "bad": "{k}: {e}", "call": "{f}({a})", "deriv": "Noise on a derivative: unit of the derivative."},
}


def specs(state: dict) -> dict:
    u = (state or {}).get("unc")
    if not isinstance(u, dict):
        return {}
    return {k: v for k, v in u.items() if isinstance(v, dict) and isinstance(v.get("parts"), list) and v["parts"]}


def noise_mode(state: dict) -> str:
    m = ((state or {}).get("unc_noise") or {}).get("mode")
    if m in ("off", "auto", "region", "manual"):
        return m
    return "manual" if "noise" in specs(state) else "off"


def active(state: dict) -> bool:
    s = specs(state)
    m = noise_mode(state)
    return "nu" in s or m in ("auto", "region") or (m == "manual" and "noise" in s)


def method(state: dict) -> dict:
    m = (state or {}).get("unc_method") or {}
    meth = m.get("method") if m.get("method") in UN.METHODS else "gum"
    try:
        p = float(m.get("p") or UN.P_DEFAULT)
    except (TypeError, ValueError):
        p = UN.P_DEFAULT
    try:
        k = float(m["k"]) if m.get("k") not in (None, "", 0) else None
    except (TypeError, ValueError):
        k = None
    return {"method": meth, "p": p, "k": k}


def _u(spec, value=0.0, unit=""):
    """(Standardunsicherheit, Freiheitsgrade) einer Angabe; (0, None) ohne Angabe."""
    if not spec:
        return 0.0, None
    try:
        d = UN.make_input({"name": "x", "value": value, "unit": unit, "parts": spec.get("parts") or []})
    except UN.UncError:
        return 0.0, None
    dof = d.get("dof")
    return float(d["u"]), (float(dof) if dof is not None and math.isfinite(float(dof)) else None)


def _g(v, lang="de"):
    s = f"{float(v):.3g}"
    return s.replace(".", ",") if lang == "de" else s


class Lin:
    """Q = value + g·ε + Σ s_k δ_k: g Empfindlichkeit auf das Rauschen je Punkt (Flächenbasis, volle Länge),
    s Empfindlichkeiten auf benannte Quellen (Achsenfehler, Grenzen, Interpolation)."""
    __slots__ = ("value", "g", "s")

    def __init__(self, value, g=None, s=None):
        self.value, self.g, self.s = float(value), g, dict(s or {})

    def lin_ratio(self, other: "Lin") -> "Lin":
        """Linearisierung von self/other (für Variablen R in eigenen Gleichungen)."""
        R = self.value / other.value
        g = None
        if self.g is not None or other.g is not None:
            n = len(self.g if self.g is not None else other.g)
            gn = self.g if self.g is not None else np.zeros(n)
            gd = other.g if other.g is not None else np.zeros(n)
            g = (gn - R * gd) / other.value
        s = {k: (self.s.get(k, 0.0) - R * other.s.get(k, 0.0)) / other.value for k in set(self.s) | set(other.s)}
        return Lin(R, g, s)


class Ctx:
    def __init__(self, a, state: dict, lang: str):
        self.a, self.lang = a, lang
        self.L = L10N.get(lang, L10N["de"])
        self.s = specs(state)
        self.m = method(state)
        self.notes: list[str] = []
        sp = a.sp
        self.x = np.asarray(sp.x, float)
        self.y = np.asarray(sp.y, float)
        self.yunit = sp.yunit
        ya = PK._absorb(self.y, self.yunit)
        self.yb = ya if ya is not None else self.y             # Basis der Flächenrechnung (wie PK.integrate)
        self.step = float(abs(np.median(np.diff(self.x)))) if len(self.x) > 1 else 1.0
        self.src: dict[str, dict] = {}                         # Quelle -> Eingangsgrösse (Wert 0)
        self.sigma, self.noise_dof, self.noise_label, self.noise_src = self._noise(state)
        if "nu" in self.s:
            self.src["dnu"] = {"name": "dnu", "value": 0.0, "unit": "cm⁻¹", "label": self.L["nu"],
                               "parts": self.s["nu"]["parts"], **({"dof": self.s["nu"]["dof"]} if self.s["nu"].get("dof") not in (None, "", "inf") else {})}
        self.results: list[dict] = []
        self.lins: dict[str, Lin] = {}                         # Variable -> Lin (für eigene Gleichungen)

    # ------------------------------------------------------------------ Rauschen
    def _noise(self, state):
        L, lang = self.L, self.lang
        mode = noise_mode(state)
        n = len(self.x)
        if mode == "auto" and n >= 30:
            q = QA.assess(self.x, self.yb, "A")
            sig = QA.effective_noise(self.x, self.yb, q)
            if float(q["sigma"]) > 0:
                return sig, None, L["noise_auto"].format(s=_g(q["sigma"], lang)), SOURCES["savitzky1964"]
        if mode == "region":
            r = ((state or {}).get("unc_noise") or {}).get("region") or []
            try:
                lo, hi = sorted((float(r[0]), float(r[1])))
            except (TypeError, ValueError, IndexError):
                lo = hi = None
            if lo is not None:
                m = (self.x >= lo) & (self.x <= hi) & np.isfinite(self.yb)
                k = int(m.sum())
                if k >= 5:
                    c = np.polyfit(self.x[m], self.yb[m], 1)
                    res = self.yb[m] - np.polyval(c, self.x[m])
                    s = float(np.sqrt(np.sum(res ** 2) / (k - 2)))
                    return (np.full(n, s), float(k - 2),
                            L["noise_reg"].format(hi=f"{hi:.0f}", lo=f"{lo:.0f}", n=k, s=_g(s, lang)), None)
                self.notes.append(L["region_bad"].format(hi=f"{hi:.0f}", lo=f"{lo:.0f}"))
        if mode == "manual" and "noise" in self.s:
            s, dof = _u(self.s["noise"])
            if s > 0:
                return np.full(n, s), dof, L["noise_man"].format(s=_g(s, lang)), None
        return None, None, "", None

    def var(self, a: Lin) -> float:
        return self.cov(a, a)

    def noise_u(self, g) -> float:
        if g is None or self.sigma is None:
            return 0.0
        return float(np.sqrt(np.sum((g * self.sigma) ** 2)))

    def cov_noise(self, g1, g2) -> float:
        if g1 is None or g2 is None or self.sigma is None:
            return 0.0
        return float(np.sum(g1 * g2 * self.sigma ** 2))

    def cov(self, a: Lin, b: Lin) -> float:
        c = self.cov_noise(a.g, b.g)
        for k in set(a.s) & set(b.s):
            if k in self.src:
                c += a.s[k] * b.s[k] * _u(self.src[k])[0] ** 2
        return c

    # ------------------------------------------------------------------ Linearformen
    def band(self, lo, hi, base="linear"):
        """Fläche, Höhe, Lage einer Bande als Lin (gleiche Rechnung wie PK.integrate)."""
        lo, hi = sorted((float(lo), float(hi)))
        x, yb = self.x, self.yb
        idx = np.nonzero((x >= lo) & (x <= hi))[0]
        if len(idx) < 3:
            return None
        xs, ys = x[idx], yb[idx]
        n = len(idx)
        t = (xs - xs[0]) / (xs[-1] - xs[0])
        w = np.zeros(n)
        dx = np.diff(xs)
        w[:-1] += dx / 2
        w[1:] += dx / 2
        c = w.copy()
        lin = base == "linear"
        if lin:
            c[0] -= float(np.sum(w * (1 - t)))
            c[-1] -= float(np.sum(w * t))
        b = (ys[0] * (1 - t) + ys[-1] * t) if lin else np.zeros(n)
        d = ys - b
        i = int(np.argmax(d))
        ch = np.zeros(n)
        ch[i] += 1.0
        if lin:
            ch[0] -= 1 - t[i]
            ch[-1] -= t[i]
        G = np.zeros(len(x))
        G[idx] = c
        GH = np.zeros(len(x))
        GH[idx] = ch
        key = f"{base}:{lo:.4f}:{hi:.4f}"
        out = {"area": Lin(float(c @ ys), G), "height": Lin(float(d[i]), GH), "pos": Lin(float(xs[i]))}
        # Typ B: Wahl der Grenzen bzw. der Basislinie (Grenzen um ±1 Punkt)
        for what in ("area", "height"):
            vals = [out[what].value]
            for dl, dh in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                r = PK.integrate(x, self.y, lo + dl * self.step, hi + dh * self.step, self.yunit, base)
                if r.get(what) is not None:
                    vals.append(float(r[what]))
            half = (max(vals) - min(vals)) / 2
            if half > 0:
                sk = f"base:{what}:{key}"
                self.src.setdefault(sk, {"name": "b", "value": 0.0, "unit": "",
                                         "label": self.L["base"].format(w=f"{hi:.0f}–{lo:.0f}"),
                                         "parts": [{"kind": "limits", "a": half, "dist": "rect"}]})
                out[what].s[sk] = 1.0
        ik = f"interp:{key}"
        self.src.setdefault(ik, {"name": "i", "value": 0.0, "unit": "cm⁻¹", "label": self.L["interp"].format(d=_g(self.step, self.lang)),
                                 "parts": [{"kind": "resolution", "d": self.step}]})
        out["pos"].s[ik] = 1.0
        if "dnu" in self.src:
            out["pos"].s["dnu"] = -1.0                       # Ablesung = wahr + δν̃
        return out

    def _dyb(self, k):
        """d(Flächenbasis)/d(y) an Punkt k (1 bei Absorbanz)."""
        if self.yb is self.y:
            return 1.0
        yv = float(self.y[k])
        h = 1e-6 * max(1.0, abs(yv))
        f = PK._absorb(np.array([yv - h, yv + h]), self.yunit)
        return float((f[1] - f[0]) / (2 * h)) or 1.0

    def peak(self, p, n):
        """Peaklage (Parabel durch drei Punkte, peaks._shape) linearisiert."""
        x = self.x
        valley = self.yunit in ("T", "R")
        ys = -self.y if valley else self.y
        j = int(np.argmin(np.abs(x - p["x"])))
        cand = [k for k in (j - 1, j, j + 1) if 0 <= k < len(x)]
        i = max(cand, key=lambda k: ys[k])
        g = None
        if 0 < i < len(x) - 1:
            y0, y1, y2 = ys[i - 1], ys[i], ys[i + 1]
            den = y0 - 2 * y1 + y2
            if den < 0 and abs(0.5 * (y0 - y2) / den) <= 1:
                stp = (x[i + 1] - x[i - 1]) / 2
                dd = np.array([0.5 / den - 0.5 * (y0 - y2) / den ** 2, (y0 - y2) / den ** 2,
                               -0.5 / den - 0.5 * (y0 - y2) / den ** 2]) * stp * (-1.0 if valley else 1.0)
                g = np.zeros(len(x))
                for off, k in enumerate((i - 1, i, i + 1)):
                    g[k] = dd[off] / self._dyb(k)
        ik = f"interp:peak{n}"
        self.src[ik] = {"name": "i", "value": 0.0, "unit": "cm⁻¹", "label": self.L["interp"].format(d=_g(self.step, self.lang)),
                        "parts": [{"kind": "resolution", "d": self.step}]}
        s = {ik: 1.0}
        if "dnu" in self.src:
            s["dnu"] = -1.0
        return Lin(float(p["x"]), g, s)

    def call(self, fn, args):
        """Lin eines Funktionsaufrufs in eigenen Gleichungen (None: wird exakt gerechnet)."""
        try:
            args = [float(np.mean(v)) for v in args]
        except (TypeError, ValueError):
            return None
        if fn in ("area", "area0", "height") and len(args) == 2:
            b = self.band(args[0], args[1], "zero" if fn == "area0" else "linear")
            return None if b is None else b["height" if fn == "height" else "area"]
        if fn in ("A", "y") and len(args) == 1:
            order = np.argsort(self.x)
            xs = self.x[order]
            nu = args[0]
            j = int(np.clip(np.searchsorted(xs, nu) - 1, 0, len(xs) - 2))
            t = (nu - xs[j]) / (xs[j + 1] - xs[j]) if xs[j + 1] != xs[j] else 0.0
            k0, k1 = int(order[j]), int(order[j + 1])
            g = np.zeros(len(xs))
            if fn == "A":
                g[k0], g[k1] = 1 - t, t
                yy = self.yb
            else:
                g[k0], g[k1] = (1 - t) / self._dyb(k0), t / self._dyb(k1)
                yy = self.y
            val = (1 - t) * yy[k0] + t * yy[k1]
            slope = (yy[k1] - yy[k0]) / (xs[j + 1] - xs[j]) if xs[j + 1] != xs[j] else 0.0
            return Lin(float(val), g, {"dnu": float(slope)} if "dnu" in self.src else {})
        return None

    # ------------------------------------------------------------------ Auswertung
    def build(self, items, f, rid, label, unit, extra=()):
        """items: [(Schlüssel, Lin)]; f(Werte je Schlüssel) -> Ergebnis. Rauschen je Grösse als eigene Eingangsgrösse,
        untereinander korreliert; gemeinsame Quellen einmal. extra: weitere unabhängige Eingangsgrössen (Name = Schlüssel)."""
        L = self.L
        ins, corr, noise, names = [], [], [], {}
        for key, lin in items:
            un = self.noise_u(lin.g)
            if un > 0:
                nm = f"e_{key}"
                part = {"kind": "u", "u": un, "label": self.noise_label}
                if self.noise_dof:
                    part["dof"] = self.noise_dof
                if self.noise_src:
                    part["source"] = self.noise_src
                ins.append({"name": nm, "value": 0.0, "unit": unit if len(items) == 1 else "",
                            "label": f"{L['noise']} {key}" if len(items) > 1 else L["noise"], "parts": [part]})
                noise.append((nm, lin, un))
            for sk in lin.s:
                if sk in self.src and sk not in names:
                    base = self.src[sk]
                    nm = base["name"] if base["name"] == "dnu" else f"{base['name']}{len(names) + 1}"
                    names[sk] = nm
                    ins.append({**{k: v for k, v in base.items() if k != "name"}, "name": nm})
        for a_ in range(len(noise)):
            for b_ in range(a_ + 1, len(noise)):
                r = self.cov_noise(noise[a_][1].g, noise[b_][1].g) / (noise[a_][2] * noise[b_][2])
                if abs(r) > 1e-9:
                    corr.append({"a": noise[a_][0], "b": noise[b_][0], "r": float(max(-1.0, min(1.0, r)))})
        ins += list(extra)
        if not ins:
            return None
        en = {nm for nm, _l, _u in noise}

        def model(v):
            vals = {}
            for key, lin in items:
                q = lin.value
                if f"e_{key}" in en:
                    q = q + v[f"e_{key}"]
                for sk, c in lin.s.items():
                    if sk in names:
                        q = q + c * v[names[sk]]
                vals[key] = q
            for e in extra:
                vals[e["name"]] = v[e["name"]]
            return f(vals)
        try:
            r = UN.evaluate(model, ins, self.m["method"], corr=corr or None, p=self.m["p"], k=self.m["k"],
                            lang=self.lang, unit=unit, label=label, name=rid)
        except (UN.UncError, ValueError, ZeroDivisionError, FloatingPointError, TypeError) as e:
            self.notes.append(L["bad"].format(k=label, e=e))
            return None
        if not r.get("uncertain_n"):
            return None
        u = r.get("u")
        if u is None:                                       # Grösstfehler: u nach Gauss für die Weitergabe
            try:
                u = UN.evaluate(model, ins, "gauss", lang=self.lang)["u"]
            except (UN.UncError, ValueError):
                u = None
        if not u and not r.get("U"):
            return None
        return r, u

    def add(self, rid, group, label, unit, items, f, extra=()):
        got = self.build(items, f, rid, label, unit, extra)
        if not got:
            return None
        r, u = got
        out = {"id": rid, "group": group, "label": label, "unit": unit, "value": r["value"], "u": u, "res": r}
        self.results.append(out)
        return out


# ============================================================================== Ergebnisse eines Spektrums
def evaluate(a, state: dict, lang: str = "de"):
    """Budgets für Peaks, Banden und Verhältnisse; setzt a.unc_ctx für eigene Gleichungen. None ohne Angaben."""
    if not active(state):
        return None
    c = Ctx(a, state, lang)
    a.unc_ctx = c
    L = c.L
    one = lambda v: v["q"]  # noqa: E731
    for n, p in enumerate(a.peaks or [], 1):
        lin = c.peak(p, n)
        c.add(f"peak{n}", "peaks", L["peak"].format(x=f"{p['x']:.0f}"), "cm⁻¹", [("q", lin)], one)
    blins = {}
    sb = state.get("bands") or []
    for i, r in enumerate(a.bands, 1):
        if r.get("area") is None:
            continue
        base = (sb[i - 1].get("base") or "linear") if i - 1 < len(sb) and isinstance(sb[i - 1], dict) else "linear"
        bl = c.band(r["lo"], r["hi"], base)
        if bl is None:
            continue
        blins[r["name"]] = bl
        c.lins[f"B{i}"], c.lins[f"H{i}"], c.lins[f"P{i}"] = bl["area"], bl["height"], bl["pos"]
        c.add(f"band{i}-area", "bands", L["area"].format(n=r["name"]), "", [("q", bl["area"])], one)
        c.add(f"band{i}-height", "bands", L["height"].format(n=r["name"]), "", [("q", bl["height"])], one)
        c.add(f"band{i}-pos", "bands", L["pos"].format(n=r["name"]), "cm⁻¹", [("q", bl["pos"])], one)
    for i, r in enumerate(a.ratios, 1):
        if r.get("value") is None:
            continue
        nb, db = blins.get(r.get("num")), blins.get(r.get("den"))
        if not nb or not db:
            continue
        w = "area" if r.get("kind", "area") == "area" else "height"
        c.lins[f"R{i}"] = nb[w].lin_ratio(db[w])
        c.add(f"ratio{i}", "ratios", L["ratio"].format(n=r["name"]), "", [("Z", nb[w]), ("N", db[w])],
              lambda v: v["Z"] / v["N"])
    return {"method": c.m, "results": c.results, "notes": c.notes, "keys": sorted(c.s),
            "noise": {"mode": noise_mode(state), "label": c.noise_label,
                      "sigma": float(np.median(c.sigma)) if c.sigma is not None else None}}


def variables_u(a):
    """u und unc an die Variablen B/H/P/R hängen (eigene Gleichungen, geteilte Werte)."""
    unc = getattr(a, "unc", None)
    if not unc:
        return
    by = {r["id"]: r for r in unc["results"]}
    for i in range(1, len(a.bands) + 1):
        for var, rid in ((f"B{i}", f"band{i}-area"), (f"H{i}", f"band{i}-height"), (f"P{i}", f"band{i}-pos")):
            _put(a.variables, var, by.get(rid), unc)
    for i in range(1, len(a.ratios) + 1):
        _put(a.variables, f"R{i}", by.get(f"ratio{i}"), unc)


def _put(variables, var, r, unc):
    if var in variables and r and r.get("u"):
        variables[var]["u"] = float(r["u"])
        variables[var]["unc"] = {"method": unc["method"]["method"], **plain_one(r)}


def plain_one(r):
    res = r["res"]
    return {"value": r["value"], "u": r.get("u"), "U": res.get("U"), "text": res.get("text"), "method": res.get("method")}


def plain(unc) -> dict:
    return {r["id"]: plain_one(r) for r in ((unc or {}).get("results") or [])}


# ============================================================================== Eigene Gleichungen
_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
FUNCS = ("A", "y", "area", "area0", "height")


def equations(a, funcs: dict, lang: str = "de"):
    """Unsicherheit eigener Gleichungen: Variablen B/H/P/R und Funktionsaufrufe A(ν), y(ν), area(…), area0(…),
    height(…) gehen mit ihrem Rauschanteil (korreliert über gemeinsame Messpunkte), den Grenzen und dem Achsenfehler
    ein. Die Argumente der Funktionen gelten als exakt. Setzt row["unc"] und row["text_pm"]."""
    c = getattr(a, "unc_ctx", None)
    if c is None or not a.equations:
        return
    from labcalc import expr as E
    names = {}
    for k, v in a.variables.items():
        try:
            names[k] = float(v["value"] if isinstance(v, dict) else v)
        except (TypeError, ValueError, KeyError):
            continue
    callables = E.Ctx().callables() | frozenset(funcs)
    chain = []
    for row in a.equations:
        if row.get("error") or row.get("value") is None:
            continue
        try:
            node = E.parse(row["expr"], callables)
        except (E.CalcError, SyntaxError, ValueError):
            continue
        chain.append((row["sym"], node, row["expr"]))
        exprs = {s: ex for s, _n, ex in chain}
        used, todo = set(), [row["sym"]]
        while todo:
            s = todo.pop()
            for t in _TOKEN.findall(exprs.get(s, "")):
                if t in exprs and t not in used and t != s:
                    todo.append(t)
                used.add(t)
        nodes = [x for x in chain if x[0] in used or x[0] == row["sym"]]
        # Aufrufe der Reihe nach aufzeichnen
        calls = []

        def rec(name, fn):
            def w(*args):
                v = fn(*args)
                calls.append((name, args, v))
                return v
            return w
        rf = {k: (rec(k, f) if k in FUNCS else f) for k, f in funcs.items()}
        loc = dict(names)
        try:
            for sym, node, _ex in nodes:
                loc[sym] = E.evaluate(node, E.Ctx(names=dict(loc)), dict(rf))
        except Exception:  # noqa: BLE001 – Gleichung selbst ist schon ausgewertet; ohne Unsicherheit weiter
            continue
        items, extra = [], []
        for var in sorted(used):
            if var in c.lins and var in names:
                items.append((var, c.lins[var]))
            elif var in names and isinstance(a.variables.get(var), dict) and (a.variables[var].get("u") or 0) > 0:
                u = float(a.variables[var]["u"])
                extra.append({"name": var, "value": names[var], "unit": a.variables[var].get("unit") or "",
                              "label": a.variables[var].get("label") or var, "parts": [{"kind": "u", "u": u}]})
        call_keys = []
        for k, (fn, args, v) in enumerate(calls):
            lin = c.call(fn, args)
            key = c.L["call"].format(f=fn, a="; ".join(_g(x, lang) for x in args))
            if lin is not None:
                if key not in [x[0] for x in items]:
                    items.append((key, lin))
                call_keys.append(key)
            else:
                call_keys.append(None)
        if not items and not extra:
            continue
        base_vals = [v for _f, _a, v in calls]

        def model(vals, nodes=nodes, call_keys=call_keys, base_vals=base_vals):
            loc2 = dict(names)
            for k, v in vals.items():
                if k in names:
                    loc2[k] = v
            cnt = [0]

            def wrap(name, fn):
                def w(*args):
                    i = cnt[0]
                    cnt[0] += 1
                    if i < len(call_keys):
                        ck = call_keys[i]
                        return vals[ck] if ck is not None else base_vals[i]
                    return fn(*args)
                return w
            ff = {k: (wrap(k, f) if k in FUNCS else f) for k, f in funcs.items()}
            y = None
            for sym, node, _ex in nodes:
                y = E.evaluate(node, E.Ctx(names=dict(loc2)), ff)
                loc2[sym] = y
            return y
        got = c.build(items, model, f"eq-{row['sym']}", row.get("label") or row["sym"], row.get("unit") or "", extra)
        if got:
            row["unc"], _u_ = got
            row["text_pm"] = got[0]["text"]


# ============================================================================== Bericht
def report(b, unc, lang: str, prefix: str = "") -> dict | None:
    results = [dict(r["res"], name=r["id"]) for r in ((unc or {}).get("results") or [])]
    if not results:
        return None
    from labbundle import booktabs, tex_escape
    uo = UN.to_report(b, results, lang, prefix=prefix)
    de = lang == "de"
    rows = [[tex_escape(r.get("label") or r["name"]), tex_escape(r.get("text") or ""), tex_escape(r.get("method_name") or "")]
            for r in results]
    pid = prefix.rstrip("-")
    tid = f"unsicherheit{('-' + pid) if pid else ''}"
    b.add_table(tid, booktabs(["Grösse" if de else "Quantity", "Wert ± U" if de else "Value ± U",
                               "Verfahren" if de else "Method"], rows, align="lll", small=True),
                ("Messunsicherheit der Banden und Verhältnisse (Budgets in den Einzeltabellen)." if de else
                 "Measurement uncertainty of bands and ratios (budgets in the individual tables)."), cites=uo["cites"] or None)
    uo["tables"] = list(uo.get("tables") or []) + [tid]
    return uo


def methods_text(unc, uo, cite_fn, lang: str) -> str:
    if not uo:
        return ""
    de = lang == "de"
    m = ((unc or {}).get("method") or {}).get("method") or "gum"
    name = UN.NAMES["de" if de else "en"][m]
    c = cite_fn(uo.get("cites") or [])
    nz = (unc or {}).get("noise") or {}
    mode = nz.get("mode")
    if de:
        t = f"Messunsicherheiten wurden nach dem Verfahren „{name}“{c} bestimmt."
        if mode == "auto":
            t += (" Das Rauschen je Punkt wurde aus dem Rest einer Savitzky-Golay-Glättung geschätzt (wie für das "
                  "Signal-Rausch-Verhältnis, Typ A).")
        elif mode == "region":
            t += " Das Rauschen ist der quadratische Mittelwert eines bandenfreien Bereichs nach Abzug einer Geraden (Typ A)."
        elif mode == "manual":
            t += " Das Rauschen je Punkt ist angegeben."
        t += (" Flächen und Höhen sind lineare Funktionen der Messpunkte ($A = \\sum_i c_i y_i$, Trapezregel über der "
              "Geraden zwischen den Grenzen); ihre Rauschunsicherheit ist $\\sqrt{\\sum_i c_i^2\\sigma_i^2}$, die Kovarianz "
              "zweier Grössen $\\sum_i c_i c'_i \\sigma_i^2$, sodass überlappende Banden in Verhältnissen und Gleichungen "
              "korreliert bleiben. Für die Wahl der Grenzen ist die halbe Spannweite bei Grenzen um $\\pm 1$ Punkt als "
              "Rechteckverteilung angesetzt; Lagen enthalten die Wellenzahlgenauigkeit (falls angegeben) und die "
              "Interpolation zwischen Messpunkten (Punktabstand).")
    else:
        t = f"Measurement uncertainties were evaluated with the method “{name}”{c}."
        if mode == "auto":
            t += (" The noise per point was estimated from the residual of a Savitzky-Golay smooth (as for the "
                  "signal-to-noise ratio, type A).")
        elif mode == "region":
            t += " The noise is the root mean square of a band-free region after removing a straight line (type A)."
        elif mode == "manual":
            t += " The noise per point is stated."
        t += (" Areas and heights are linear functions of the data points ($A = \\sum_i c_i y_i$, trapezoidal rule above "
              "the line between the limits); their noise uncertainty is $\\sqrt{\\sum_i c_i^2\\sigma_i^2}$ and the covariance "
              "of two quantities $\\sum_i c_i c'_i \\sigma_i^2$, so overlapping bands stay correlated in ratios and equations. "
              "The choice of limits contributes half the spread for limits moved by $\\pm 1$ point (rectangular); "
              "positions include the wavenumber accuracy (if stated) and the interpolation between data points (spacing).")
    return t
