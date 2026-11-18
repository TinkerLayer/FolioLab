"""Auswertealgorithmus (Spezifikation Abschnitte 3, 4 und 7).

Einstieg: run(flps_file, Config) -> Result. Jeder Schritt ist als eigene Funktion testbar.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

import numpy as np

from . import alloys as alloys_mod
from .parser import FlpsFile
from .prepare import Prepared, prepare

# --- 3.1 Probengeometrie ----------------------------------------------------------
SPECIMEN_PATH = Path(__file__).resolve().parent.parent / "data" / "specimens.json"


def load_shapes(path: str | Path | None = None) -> dict:
    """Genormte Probenformen aus data/specimens.json, Name -> Masse."""
    raw = json.loads(Path(path or SPECIMEN_PATH).read_text(encoding="utf-8"))
    out = {}
    for p in raw["proben"]:
        e = {k: p.get(k) for k in ("b", "d", "L0", "h", "l3", "l1", "b2", "r", "h_min", "h_max")}
        e.update(section=p.get("section", "rechteckig"), note=p.get("note", ""), norm=p.get("norm", ""),
                 gruppe=p.get("gruppe", ""), werkstoffe=p.get("werkstoffe", []))
        out[p["name"]] = e
    return out


SHAPES = load_shapes()
MANUAL_SHAPE = "Frei"

YIELD_DETENTS = (0.005, 0.01, 0.02, 0.05)
PLATEAU_FRACTION = 0.8      # Plateau: von 80 % bis 100 % der Zeit vom Kraftanstieg t0 bis zum Maximum

PHASES = ["Setzen", "elastisch", "plastisch", "Abfall", "Bruch", "nach Bruch"]


@dataclass
class Config:
    # Probengeometrie
    specimen_mode: str = "norm"           # "norm" (Normprobe waehlen) oder "manuell"
    shape: str = "Frei"
    section: str = "rechteckig"          # "rechteckig", "rund" oder "rohr"
    width_mm: float | None = None         # Stegbreite b
    thickness_mm: float | None = None
    diameter_mm: float | None = None
    outer_d_mm: float | None = None       # Rohr: Aussendurchmesser
    wall_mm: float | None = None          # Rohr: Wanddicke
    a0_mm2: float | None = None           # direkt eingegeben, ueberschreibt die Rechnung
    l0_mm: float | None = None
    # Pruefbedingungen
    speed_mm_min: float | None = None
    displacement_source: str | None = None   # "probe", "traverse" oder None
    material: str = ""
    material_ref: str | None = None       # gewaehlter Referenzwerkstoff aus data/alloys.json
    compare_group: str | None = None      # Vergleichsgruppe der Rangliste, leer = Aluminium
    batch: str = ""
    operator: str = ""
    remark: str = ""
    # Auswerteparameter (3.3)
    slope_window_s: float = 1.0
    tol_stress_mpa: float = 1.0
    tol_force_n: float = 0.20
    yield_threshold: float = 0.02
    break_upper: float = 0.10
    break_lower: float = 0.01
    hold_threshold: float = 0.90
    fit_start_points: int = 3
    # Zusätzlich im Spannungs-Dehnungs-Feld gezeigte Werkstoffe (Namen), gleich welcher Gruppe
    extra_refs: list | None = None
    # Eigene Gleichungen (vollständige Einträge, damit der Bericht sie auch nach Änderungen reproduziert)
    equations: list | None = None
    # Werte anderer Umgebungen (Verbindung in der Übersicht), als zusätzliche Variablen der Gleichungen
    ext_values: list | None = None

    @classmethod
    def from_dict(cls, d: dict | None) -> "Config":
        d = d or {}
        kw = {}
        for f in fields(cls):
            if f.name not in d:
                continue
            v = d[f.name]
            if f.name == "extra_refs":
                v = [str(x) for x in (v or []) if isinstance(x, str) and x.strip()][:20] or None
                kw[f.name] = v
                continue
            if f.name in ("equations", "ext_values"):
                v = [x for x in (v or []) if isinstance(x, dict)][:200 if f.name == "ext_values" else 60] or None
                kw[f.name] = v
                continue
            if isinstance(v, str) and f.type in ("float | None", "float", "int"):
                v = v.strip().replace(",", ".")
                v = None if v == "" else float(v)
            if v is not None and f.type in ("float | None", "float"):
                v = float(v)
            if v is not None and f.type == "int":
                v = int(v)
            if f.type in ("float", "int") and v is None:
                continue
            if f.type == "str | None" and v == "":
                v = None
            if f.type == "str" and v is None:
                v = ""
            kw[f.name] = v
        return cls(**kw)

    def to_dict(self) -> dict:
        return asdict(self)

    def area(self) -> float | None:
        """A0 in mm^2: Direkteingabe vor Rechnung aus der Geometrie."""
        if self.a0_mm2 is not None and self.a0_mm2 > 0:
            return self.a0_mm2
        if self.section == "rund":
            if self.diameter_mm and self.diameter_mm > 0:
                return math.pi * self.diameter_mm ** 2 / 4.0
            return None
        if self.section == "rohr":
            D, t = self.outer_d_mm, self.wall_mm
            if D and t and D > 0 and 0 < t <= D / 2:
                return math.pi / 4.0 * (D ** 2 - (D - 2 * t) ** 2)
            return None
        if self.width_mm and self.thickness_mm and self.width_mm > 0 and self.thickness_mm > 0:
            return self.width_mm * self.thickness_mm
        return None

    def area_source(self) -> str:
        if self.a0_mm2 is not None and self.a0_mm2 > 0:
            return "direkt eingegeben"
        if self.area() is None:
            return "fehlt"
        return {"rund": "π d² / 4", "rohr": "π/4 (D² − (D − 2t)²)"}.get(self.section, "b × Dicke")

    def norm_deviations(self) -> list[str]:
        """Masse, die im Normmodus von der gewaehlten Normprobe abweichen."""
        sh = SHAPES.get(self.shape)
        if self.specimen_mode != "norm" or not sh:
            return []
        out = []
        for key, val, label in (("b", self.width_mm, "b"), ("d", self.diameter_mm, "d"), ("L0", self.l0_mm, "L0")):
            if sh.get(key) is not None and val is not None and abs(val - sh[key]) > 1e-9:
                out.append(f"{label} = {fmt(val, 2)} mm statt {fmt(sh[key], 2)} mm")
        return out

    @property
    def speed_mm_s(self) -> float | None:
        return self.speed_mm_min / 60.0 if self.speed_mm_min and self.speed_mm_min > 0 else None


# --- 4.1 Steigung -------------------------------------------------------------------
def sliding_slope(t: np.ndarray, y: np.ndarray, window_points: int) -> np.ndarray:
    """Differenzenquotient ueber ein gleitendes Fenster, an den Raendern beschnitten."""
    n = len(y)
    h = max(1, window_points // 2)
    s = np.zeros(n)
    for i in range(n):
        a, b = max(0, i - h), min(n - 1, i + h)
        s[i] = (y[b] - y[a]) / (t[b] - t[a]) if t[b] > t[a] else 0.0
    return s


# --- 4.2 Fitfenster -----------------------------------------------------------------
@dataclass
class LineFit:
    lo: int
    hi: int
    k: float
    q: float
    r2: float
    max_dev: float

    @property
    def n(self) -> int:
        return self.hi - self.lo + 1


def line_fit(t: np.ndarray, y: np.ndarray, lo: int, hi: int) -> LineFit:
    x, v = t[lo:hi + 1], y[lo:hi + 1]
    k, q = np.polyfit(x, v, 1)
    r = v - (k * x + q)
    ss = float(np.sum((v - v.mean()) ** 2))
    r2 = 1.0 - float(np.sum(r ** 2)) / ss if ss > 0 else 1.0
    return LineFit(lo, hi, float(k), float(q), r2, float(np.max(np.abs(r))))


def grow_fit_window(t: np.ndarray, y: np.ndarray, center: int, tol: float, start: int = 3) -> LineFit:
    """Start mit `start` Punkten beidseits der groessten Steigung, abwechselnd links und rechts
    wachsen, solange die groesste Abweichung unter der Toleranz bleibt.

    Gierige Suche: jeder Schritt wird nur behalten, wenn die neue Gerade die Toleranz einhaelt, und die Suche endet,
    sobald keine Seite mehr wachsen kann. Das Ergebnis ist ein zusammenhaengendes Fenster um die Startstelle, nicht
    notwendig das laengste Fenster, das die Toleranz einhaelt."""
    n = len(y)
    lo, hi = max(0, center - start), min(n - 1, center + start)
    best = line_fit(t, y, lo, hi)
    while True:
        grew = False
        for side in (-1, 1):  # abwechselnd links, rechts
            nlo, nhi = (lo - 1, hi) if side < 0 else (lo, hi + 1)
            if nlo < 0 or nhi >= n:
                continue
            cand = line_fit(t, y, nlo, nhi)
            if cand.max_dev < tol:
                lo, hi, best = nlo, nhi, cand
                grew = True
        if not grew:
            return best


# --- 4.4 Fliessbeginn ---------------------------------------------------------------
def find_yield(t: np.ndarray, y: np.ndarray, fit: LineFit, threshold_abs: float) -> int | None:
    dev = (fit.k * t + fit.q) - y
    for i in range(fit.hi + 1, len(y)):
        if dev[i] > threshold_abs:
            return i
    return None


# --- 4.7 Haltezeit ------------------------------------------------------------------
def hold_run(t: np.ndarray, y: np.ndarray, imax: int, limit: float) -> dict:
    """Haltezeit: zusammenhaengender Abschnitt um das Maximum, in dem y >= limit bleibt.

    dauer = t(letzter Punkt) - t(erster Punkt) dieses Abschnitts; ein Punkt unter der Grenze beendet ihn. Zusaetzlich
    (nur zur Information): spanne = erster bis letzter Punkt ueber der Grenze ueberhaupt (frühere Definition, schliesst
    Einbrueche ein), summe = Summe der Dauern aller Abschnitte ueber der Grenze, abschnitte = deren Anzahl."""
    mask = np.asarray(y) >= limit
    idx = np.where(mask)[0]
    out = {"dauer": 0.0, "von": None, "bis": None, "idx_von": None, "idx_bis": None,
           "spanne": float(t[idx[-1]] - t[idx[0]]) if len(idx) else 0.0, "summe": 0.0, "abschnitte": 0}
    if not len(idx):
        return out
    starts = idx[np.concatenate([[True], np.diff(idx) > 1])]
    ends = idx[np.concatenate([np.diff(idx) > 1, [True]])]
    out["abschnitte"] = int(len(starts))
    out["summe"] = float(np.sum(t[ends] - t[starts]))
    if not mask[imax]:
        return out
    k = int(np.searchsorted(starts, imax, side="right") - 1)
    i0, i1 = int(starts[k]), int(ends[k])
    out.update(dauer=float(t[i1] - t[i0]), von=float(t[i0]), bis=float(t[i1]), idx_von=i0, idx_bis=i1)
    return out


# --- Ergebnis -----------------------------------------------------------------------
@dataclass
class Result:
    source: str
    name: str
    config: Config
    device: dict
    prep: Prepared
    mode: str                     # "Spannung" oder "Kraft"
    a0: float | None
    l0: float | None
    v_mm_s: float | None
    unit: str                     # "MPa" oder "N"
    t: np.ndarray                 # feine Zeit im aktiven Abschnitt
    y: np.ndarray                 # Auswertegroesse (sigma oder |F|)
    force: np.ndarray             # |F| im aktiven Abschnitt
    slope: np.ndarray
    window_points: int
    fit: LineFit
    t0: float
    strain: np.ndarray | None     # dimensionslos, aktiver Abschnitt
    yield_idx: int | None
    yield_table: list[dict]
    imax: int
    break_idx: int | None         # Index der Bruchkraft (Vorgaenger des Lastabfalls)
    drop_idx: int | None          # erster Punkt des Lastabfalls
    phases: np.ndarray            # Phasencode je Messpunkt (alle Punkte)
    kv: dict                      # Kennwerte
    warnings: list[dict]
    comparison: dict | None
    e_schein_gpa: float | None
    alloys: list = field(default_factory=list)          # Vergleichsgruppe
    all_alloys: list = field(default_factory=list)      # gesamte Datenbank
    reference: object = None                            # gewaehlter Referenzwerkstoff (Alloy) oder None
    ref_cmp: dict | None = None
    group: str = "Aluminium"
    extras: list = field(default_factory=list)          # zusätzlich eingeblendete Werkstoffe (Alloy)
    equations: list = field(default_factory=list)       # ausgewertete eigene Gleichungen (labcalc.formulas)
    variables: dict = field(default_factory=dict)       # Messwerte als Variablen für die Gleichungen

    @property
    def shape_info(self) -> dict:
        return SHAPES.get(self.config.shape, {})

    # Hilfsgroessen
    def to_force(self, v: float | None) -> float | None:
        if v is None:
            return None
        return v * self.a0 if self.mode == "Spannung" else v

    def phase_bounds(self) -> list[dict]:
        out = []
        n_all = len(self.phases)
        i = 0
        while i < n_all:
            j = i
            while j + 1 < n_all and self.phases[j + 1] == self.phases[i]:
                j += 1
            out.append({"phase": PHASES[int(self.phases[i])], "von": i, "bis": j,
                        "t_von": float(self.prep.t_fine[i]), "t_bis": float(self.prep.t_fine[j])})
            i = j + 1
        return out


def _warn(lst: list, code: str, text: str, level: str = "warn"):
    lst.append({"code": code, "level": level, "text": text})


TEXT_7_2 = ("Der Modul ist scheinbar: der Weg stammt aus der Traverse (oder ist nicht dokumentiert) und "
            "enthält die Nachgiebigkeit von Einspannung und Rahmen. Bei kurzen Messlängen überwiegt dieser "
            "Anteil, der scheinbare Modul liegt dann um ein Vielfaches unter dem wahren. Kein Werkstoffkennwert.")
TEXT_7_3 = ("Einschnürung ist nicht belegt: gemessen ist nur, dass die Kraft nach dem Maximum zurückgeht. "
            "Dieselbe Form entsteht durch Rissfortschritt, Herausrutschen aus der Einspannung oder Relaxation. "
            "Nur die Bruchfläche entscheidet.")
TEXT_7_4 = ("Elastisch und plastisch sind ausgelegt: die Grenze stammt aus einer gesetzten Schwelle von {thr} "
            "auf der Kraftkurve, nicht aus einer Dehnungsmessung. Die Schwelle ist eine Festlegung, keine Norm; "
            "der Wert ist keine Rp0,2.")
TEXT_7_5 = ("Die Belastungsart prägt die Kurve: ohne dokumentierte Vorschubgeschwindigkeit lässt sich ein "
            "Fliessplateau nicht von der Grenze dessen trennen, was von Hand aufgebracht wurde.")
TEXT_7_1 = ("Ohne Querschnitt keine Spannung: A0 fehlt, die App rechnet in Kraft. Spannungen, Vergleiche und "
            "Rangliste sind ausgeblendet, eine Kraft lässt sich nicht mit einer Festigkeit vergleichen.")


def fmt(v, nd=1, unit: str = "") -> str:
    """Zahl mit Dezimalkomma."""
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return "–"
    s = f"{v:.{nd}f}".replace(".", ",").replace("-", "−")
    return f"{s} {unit}".rstrip() if unit else s


def pct(v: float) -> str:
    return fmt(v * 100, 1 if (v * 100) % 1 else 0, "%")


def _fix_dataset_geometry(f: FlpsFile, cfg: Config, warnings: list) -> None:
    """I-03: Masse, mit denen ein Datensatz übersetzt wurde, bleiben fest – sonst stimmten Spannung (F = σ·A0),
    Dehnung (ΔL = ε·L0) oder die Zeitachse (t = Σ|ΔL|/v) nicht mehr. Eine andere Eingabe wird ersetzt und gemeldet."""
    o = getattr(f, "origin", None)
    if not o:
        return
    g, roles = o.get("geometry") or {}, o.get("roles") or {}
    fixed = []
    if (roles.get("load") or {}).get("q") == "stress" and g.get("a0_mm2"):
        fixed.append(("a0_mm2", "A0", "mm²"))
    if (roles.get("ext") or {}).get("q") == "strain" and g.get("l0_mm"):
        fixed.append(("l0_mm", "L0", "mm"))
    if o.get("time_from") == "elongation" and g.get("speed_mm_min"):
        fixed.append(("speed_mm_min", "v", "mm/min"))
    for k, lab, u in fixed:
        want = float(g[k])
        have = getattr(cfg, k)
        if k == "a0_mm2" and have is None:
            have = cfg.area()
        if have is None or abs(have - want) > 1e-9 * max(1.0, abs(want)):
            if have is not None:
                _warn(warnings, "I-03", f"{lab} bleibt {fmt(want, 4 if k == 'a0_mm2' else 2, u)}: damit wurde der Datensatz "
                                        f"übersetzt (eingegeben: {fmt(have, 4 if k == 'a0_mm2' else 2, u)}).", "info")
            if k == "a0_mm2":
                cfg.a0_mm2 = want
            else:
                setattr(cfg, k, want)


def run(f: FlpsFile, cfg: Config | None = None, alloy_list: list | None = None) -> Result:
    cfg = cfg or Config()
    if alloy_list is None:
        alloy_list = alloys_mod.load_alloys()
    warnings: list[dict] = []
    _fix_dataset_geometry(f, cfg, warnings)

    prep = prepare(f, cfg.break_upper, cfg.break_lower)
    n = prep.n_active
    t = prep.t_fine[:n] - prep.t_fine[0]
    force = prep.force_abs[:n]

    a0 = cfg.area()
    l0 = cfg.l0_mm if cfg.l0_mm and cfg.l0_mm > 0 else None
    v = cfg.speed_mm_s
    mode = "Spannung" if a0 else "Kraft"
    unit = "MPa" if a0 else "N"
    y = force / a0 if a0 else force.copy()
    tol = cfg.tol_stress_mpa if a0 else cfg.tol_force_n
    resolution = prep.resolution / a0 if a0 else prep.resolution

    # 4.1 / 4.2
    wp = max(2, int(round(prep.rate_hz * cfg.slope_window_s))) if math.isfinite(prep.rate_hz) else 10
    slope = sliding_slope(t, y, wp)
    center = int(np.argmax(slope))
    fit = grow_fit_window(t, y, center, tol, cfg.fit_start_points)

    # 4.3
    t0 = -fit.q / fit.k if fit.k else 0.0

    # 4.5
    imax = int(np.argmax(y))
    ymax = float(y[imax])

    # 4.4
    thr_abs = cfg.yield_threshold * ymax
    yield_idx = find_yield(t, y, fit, thr_abs)
    yield_table = []
    for d in YIELD_DETENTS:
        yi = find_yield(t, y, fit, d * ymax)
        yield_table.append({"schwelle": d, "idx": yi,
                            "y": float(y[yi]) if yi is not None else None,
                            "F": float(force[yi]) if yi is not None else None,
                            "t": float(t[yi]) if yi is not None else None})
    if thr_abs < 2 * resolution:
        _warn(warnings, "4.4", f"Schwelle des Fliessbeginns ({fmt(thr_abs, 2, unit)}) liegt unter dem Doppelten "
                               f"der Anzeigeauflösung ({fmt(2 * resolution, 2, unit)}) und löst auf Rauschen aus.")

    # 4.6
    drop_idx = prep.break_index
    break_idx = drop_idx - 1 if drop_idx is not None else None

    # Phasen
    phases = np.full(prep.n_total, 5, dtype=int)
    phases[:n] = 0
    phases[fit.lo:n] = 1
    if yield_idx is not None:
        phases[yield_idx:n] = 2
    phases[imax:n] = 3
    if drop_idx is not None:
        phases[drop_idx] = 4

    # Dehnung (2.5)
    strain = (t - t0) * v / l0 if (v and l0) else None

    # 4.7 Abgeleitete Kennwerte
    kv: dict = {}
    kv["n_total"] = prep.n_total
    kv["n_active"] = n
    kv["n_cut"] = prep.n_cut
    kv["rate_hz"] = prep.rate_hz
    kv["dt_s"] = prep.dt
    kv["test_type"] = prep.test_type
    kv["fit"] = {"t_von": float(t[fit.lo]), "t_bis": float(t[fit.hi]), "n": fit.n, "lo": fit.lo, "hi": fit.hi,
                 "k": fit.k, "q": fit.q, "r2": fit.r2, "max_dev": fit.max_dev, "tol": tol,
                 "k_N_s": fit.k * a0 if a0 else fit.k, "q_N": fit.q * a0 if a0 else fit.q}
    kv["t0"] = t0
    kv["max"] = {"idx": imax, "y": ymax, "F": float(force[imax]), "t": float(t[imax]),
                 "uhrzeit": prep.timestamps[imax].strftime("%H:%M:%S")}
    if yield_idx is not None:
        kv["yield"] = {"idx": yield_idx, "y": float(y[yield_idx]), "F": float(force[yield_idx]),
                       "t": float(t[yield_idx]), "schwelle": cfg.yield_threshold,
                       "uhrzeit": prep.timestamps[yield_idx].strftime("%H:%M:%S")}
        kv["ratio"] = ymax / float(y[yield_idx])
    else:
        kv["yield"] = None
        kv["ratio"] = None
        _warn(warnings, "4.4", "Kein Fliessbeginn gefunden: die Abweichung zur Geraden überschreitet die Schwelle nie.")
    if break_idx is not None:
        yb = float(y[break_idx])
        kv["break"] = {"idx": break_idx, "drop_idx": drop_idx, "y": yb, "F": float(force[break_idx]),
                       "t": float(t[break_idx]), "uhrzeit": prep.timestamps[break_idx].strftime("%H:%M:%S")}
        kv["drop"] = {"abs": ymax - yb, "abs_F": float(force[imax] - force[break_idx]),
                      "pct": (ymax - yb) / ymax * 100.0, "dauer": float(t[break_idx] - t[imax])}
    else:
        kv["break"] = None
        kv["drop"] = None
        _warn(warnings, "4.6", "Kein Bruch erkannt: die Kraft fällt nie unter das untere Bruchkriterium. "
                               "Der aktive Abschnitt endet am letzten Messpunkt.", "info")
    # Haltezeit: zusammenhaengender Abschnitt um das Maximum über der Halteschwelle (Einbrüche beenden ihn)
    kv["hold"] = {"schwelle": cfg.hold_threshold, "grenze": cfg.hold_threshold * ymax,
                  **hold_run(t, y, imax, cfg.hold_threshold * ymax)}
    # Plateau: letzte 20 % der Zeit bis zum Maximum, gezählt ab dem Kraftanstieg t0 (wie tmax und die Dehnung)
    tm = float(t[imax])
    t_ref = max(float(t0), 0.0)
    t_von = t_ref + PLATEAU_FRACTION * (tm - t_ref)
    pm = (t >= t_von) & (t <= tm)
    kv["plateau"] = {"t_von": t_von, "t_bis": tm, "t_ref": t_ref, "anteil": PLATEAU_FRACTION,
                     "mittel": float(y[pm].mean()) if (pm.any() and tm > t_ref) else None}
    kv["phases"] = None  # wird unten gefuellt
    kv["break_duration_text"] = (f"< {fmt(prep.dt, 1, 's')} (ein Abtastintervall, bei {fmt(prep.rate_hz, 1, 'Hz')} "
                                 f"nicht aufgelöst)") if break_idx is not None else "–"
    if a0:
        kv["Rm"] = ymax
    if strain is not None:
        # Gesamtdehnungen unter Last (ISO 6892-1: Agt bei Höchstkraft, At beim Bruch) und die plastischen Anteile
        # Ag = Agt − y_max/m_E, A = At − y_Bruch/m_E (Extensometerverfahren: der elastische Anteil wird abgezogen).
        # m_E ist die Steigung des linearen Abschnitts in derselben Dehnung (dy/dε = k·L0/v), also dieselbe
        # Nachgiebigkeit wie in der gemessenen Dehnung.
        m_e = fit.k * l0 / v if fit.k > 0 else None
        agt = float(strain[imax] * 100)
        at = float(strain[break_idx] * 100) if break_idx is not None else None
        kv["strain_max_pct"] = agt                 # alter Schlüssel, = Agt
        kv["strain_break_pct"] = at                # alter Schlüssel, = At
        kv["Agt_pct"] = agt
        kv["At_pct"] = at
        kv["Ag_pct"] = agt - 100.0 * ymax / m_e if m_e else None
        kv["A_pct"] = (at - 100.0 * float(y[break_idx]) / m_e) if (m_e and at is not None) else None
        kv["E_fit"] = m_e                          # MPa (Spannung) bzw. N (Kraft) je Dehnung 1

    # 4.8 scheinbarer Modul
    e_schein = None
    if v and l0 and a0:
        k_n = fit.k * a0 if a0 else fit.k
        e_schein = k_n * (1.0 / v) * (l0 / a0) / 1000.0
    kv["E_schein_GPa"] = e_schein

    # 5.4 Vergleich innerhalb der Vergleichsgruppe
    reference = alloys_mod.find(alloy_list, cfg.material_ref)
    group = cfg.compare_group or (reference.category if reference else alloys_mod.DEFAULT_GROUP)
    group_list = alloys_mod.select_group(alloy_list, group)
    comparison = None
    ref_cmp = None
    if a0:
        ys = kv["yield"]["y"] if kv["yield"] else None
        comparison = alloys_mod.compare(ymax, ys, float(force[imax]), group_list, group)
        ref_cmp = alloys_mod.reference_comparison(ymax, ys, e_schein, reference)
    if reference is not None and not a0:
        ref_cmp = alloys_mod.reference_comparison(None, None, None, reference)
        # Rueckrechnung: Flaeche, bei der Fmax genau dem Rm des Referenzwerkstoffs entspraeche
        ref_cmp["A_needed_mm2"] = float(force[imax]) / reference.rm
        ref_cmp["d_equiv_mm"] = math.sqrt(4.0 * ref_cmp["A_needed_mm2"] / math.pi)

    # --- 7 Pflichtwarnungen ---------------------------------------------------------
    if not a0:
        _warn(warnings, "7.1", TEXT_7_1)
    if e_schein is not None or cfg.displacement_source != "probe":
        if cfg.displacement_source != "probe":
            _warn(warnings, "7.2", TEXT_7_2)
    if e_schein is not None and group_list:
        emin, emax = alloys_mod.e_range(group_list)
        if e_schein < 0.5 * emin:
            _warn(warnings, "7.2", f"Scheinbarer Modul {fmt(e_schein, 1, 'GPa')} liegt um mehr als die Hälfte unter "
                                   f"dem Bereich der Vergleichsgruppe {group} ({fmt(emin, 1)} bis {fmt(emax, 1, 'GPa')}). "
                                   "Das ist die Nachgiebigkeit des Aufbaus, nicht der Werkstoff.")
    _warn(warnings, "7.3", TEXT_7_3, "info")
    _warn(warnings, "7.4", TEXT_7_4.format(thr=pct(cfg.yield_threshold) + (" von Rm" if a0 else " von Fmax")), "info")
    if not v:
        _warn(warnings, "7.5", TEXT_7_5)
    shape = SHAPES.get(cfg.shape, {}) if cfg.specimen_mode == "norm" else {}
    h = cfg.thickness_mm if cfg.section == "rechteckig" else None
    if shape.get("norm") == "ISO 527-2" and h is not None and h < 1.0:
        _warn(warnings, "7.6", "Dicke unter 1 mm bei einer Probenform nach ISO 527-2: ISO 527-2 schliesst Folien und "
                               "Platten unter 1 mm aus, dafür gilt ISO 527-3. Für Metalle ist ISO 6892-1 zuständig. "
                               "Die Geometrie bleibt benutzbar, nur der Normbezug stimmt nicht.")
    elif shape.get("norm") == "ISO 527-2":
        _warn(warnings, "7.6", "ISO 527-2 gilt für Kunststoffe. Für metallische Werkstoffe ist ISO 6892-1 zuständig.", "info")
    if shape.get("h_max") is not None and h is not None and h >= shape["h_max"]:
        _warn(warnings, "7.6", f"Dicke {fmt(h, 2, 'mm')} bei {cfg.shape}: die Norm {shape['norm']} gilt für Dicken "
                               f"unter {fmt(shape['h_max'], 0, 'mm')}. Der Normbezug stimmt nicht.")
    if shape and reference is not None and shape.get("werkstoffe") and reference.category not in shape["werkstoffe"]:
        _warn(warnings, "7.6", f"Die Probenform {cfg.shape} ({shape.get('norm') or 'ohne Norm'}) ist für "
                               f"{', '.join(shape['werkstoffe'])} gedacht, der Referenzwerkstoff gehört zu "
                               f"{reference.category}. Die Geometrie bleibt benutzbar, nur der Normbezug stimmt nicht.",
              "info")
    dev = cfg.norm_deviations()
    if dev:
        _warn(warnings, "3.1", f"Masse weichen von der Normprobe {cfg.shape} ab: {'; '.join(dev)}.", "info")
    if cfg.specimen_mode == "manuell":
        _warn(warnings, "3.1", "Manuelle Probenabmessungen, kein Normbezug.", "info")
    _warn(warnings, "7.7", f"Zeitangaben tragen die Unsicherheit eines Abtastintervalls (≈ {fmt(prep.dt, 1, 's')}). "
                           "Der Bruchvorgang selbst ist nicht aufgelöst.", "info")
    # Einheiten (1.4)
    if not f.force_unit_confirmed:
        _warn(warnings, "1.4", f"Krafteinheit '{f.force_unit}' (Code {f.force_unit_code}) ist unbestätigt.")
    plaus = f.plausibility_warning()
    if plaus:
        _warn(warnings, "1.4", plaus, "error")

    device = {
        "model": f.model_name, "serial": f.serial_number, "comment": f.comment,
        "operator_dept": f.meta_text("operator_dept"), "operator_name": f.meta_text("operator_name"),
        "condition": f.meta_text("condition_name"),
        "force_unit": f.force_unit, "force_unit_code": f.force_unit_code,
        "force_unit_confirmed": f.force_unit_confirmed,
        "displacement_unit": f.displacement_unit, "displacement_unit_code": f.displacement_unit_code,
        "displacement_unit_confirmed": f.displacement_unit_confirmed,
        "displacement_all_zero": bool(np.all(prep.displacement == 0)),
        "start": prep.timestamps[0].strftime("%d.%m.%Y %H:%M:%S"),
        "end": prep.timestamps[-1].strftime("%d.%m.%Y %H:%M:%S"),
        "date": prep.timestamps[0].strftime("%d.%m.%Y"),
        "resolution": prep.resolution,
        "origin": getattr(f, "origin", None),      # I-03: aus einem Datensatz (sonst None = .flps-Datei)
    }
    if device["origin"]:
        o = device["origin"]
        if o.get("time_from") == "elongation":
            _warn(warnings, "I-03", "Aus einem Datensatz: die Zeitachse ist aus dem Weg und der Prüfgeschwindigkeit "
                                    "berechnet (t = Σ|ΔL| / v); Dehnung und Modul folgen dem gemessenen Weg.", "info")
        for n in o.get("notes") or []:
            _warn(warnings, "I-03", str(n) + ".", "info")

    import os
    res = Result(
        source=f.path, name=os.path.splitext(os.path.basename(f.path))[0] if f.path else "Messung",
        config=cfg, device=device, prep=prep, mode=mode, a0=a0, l0=l0, v_mm_s=v, unit=unit,
        t=t, y=y, force=force, slope=slope, window_points=wp, fit=fit, t0=t0, strain=strain,
        yield_idx=yield_idx, yield_table=yield_table, imax=imax, break_idx=break_idx, drop_idx=drop_idx,
        phases=phases, kv=kv, warnings=warnings, comparison=comparison, e_schein_gpa=e_schein,
        alloys=group_list, all_alloys=alloy_list, reference=reference, ref_cmp=ref_cmp, group=group,
    )
    kv["phases"] = res.phase_bounds()
    seen = {a.name for a in group_list}
    for nm in cfg.extra_refs or []:
        a = alloys_mod.find(alloy_list, nm)
        if a is not None and a.name not in seen:
            res.extras.append(a)
            seen.add(a.name)
    res.variables = equation_variables(res)
    if cfg.ext_values:
        F = _labcalc()
        if F is not None:
            F.merge_ext(res.variables, cfg.ext_values)        # Werte anderer Umgebungen (Verbindung)
    if cfg.equations:
        res.equations = evaluate_equations(cfg.equations, res.variables)
    return res


# --- Eigene Gleichungen -----------------------------------------------------------------
def _labcalc():
    try:
        from labcalc import formulas
    except ImportError:  # ausserhalb des Hubs gestartet: SDK aus dem Suite-Ordner holen
        import sys
        p = Path(__file__).resolve().parents[3] / "sdk" / "python"
        if not p.is_dir():
            return None
        sys.path.insert(0, str(p))
        try:
            from labcalc import formulas
        except ImportError:
            return None
    return formulas


def equation_variables(r: "Result") -> dict:
    """Kennwerte einer Messung als Variablen für eigene Gleichungen: Name -> {value, unit, label}."""
    kv = r.kv
    v: dict = {}

    def put(name, value, unit, label):
        if value is not None and math.isfinite(float(value)):
            v[name] = {"value": float(value), "unit": unit, "label": label}

    m = kv["max"]
    put("Fmax", m["F"], "N", "Maximalkraft")
    put("tmax", m["t"] - r.t0, "s", "Zeit bis zum Maximum (ab Kraftanstieg)")
    if r.a0:
        put("Rm", kv.get("Rm"), "MPa", "Zugfestigkeit")
    y = kv.get("yield")
    if y:
        put("Fy", y["F"], "N", "Kraft bei Fliessbeginn (Schwelle, keine Rp0,2)")
        if r.a0:
            put("sy", y["y"], "MPa", "Spannung bei Fliessbeginn (Schwelle, keine Rp0,2)")
    br = kv.get("break")
    if br:
        put("Fbreak", br["F"], "N", "Kraft vor dem Bruch")
        if r.a0:
            put("sbreak", br["y"], "MPa", "Spannung vor dem Bruch")
    if kv.get("drop"):
        put("drop", kv["drop"]["pct"], "%", "Abfall Maximum bis Bruch")
    put("hold", kv["hold"]["dauer"], "s", "Haltezeit über der Halteschwelle (zusammenhängend um das Maximum)")
    put("ratio", kv.get("ratio"), "", "Verhältnis Maximum/Fliessbeginn (Schwelle, keine Rp0,2)")
    put("E", r.e_schein_gpa, "GPa", "Elastizitätsmodul (scheinbar)")
    put("A0", r.a0, "mm²", "Ausgangsquerschnitt")
    put("L0", r.l0, "mm", "Messlänge")
    put("v", r.config.speed_mm_min, "mm/min", "Prüfgeschwindigkeit")
    put("k", kv["fit"]["k_N_s"], "N/s", "Steigung des linearen Abschnitts")
    if r.strain is not None:
        put("Agt", kv.get("Agt_pct"), "%", "Gesamtdehnung bei Höchstkraft Agt")
        put("Ag", kv.get("Ag_pct"), "%", "plastische Dehnung bei Höchstkraft Ag (Agt ohne elastischen Anteil)")
        put("At", kv.get("At_pct"), "%", "Gesamtdehnung beim Bruch At (unter Last)")
        put("A", kv.get("A_pct"), "%", "Bruchdehnung A (At ohne elastischen Anteil beim Bruch)")
    w = work_to_break(r)
    if w is not None:
        put("Wbreak", w[0], "J", "Arbeit bis zum Bruch " + w[1])
    ref = r.reference
    if ref is not None:
        put("Rm_ref", ref.rm, "MPa", f"Rm von {ref.name}")
        if ref.rp:
            put("Rp_ref", ref.rp, "MPa", f"Rp0,2 von {ref.name}")
        put("A_ref", ref.a_pct, "%", f"Bruchdehnung von {ref.name}")
        put("E_ref", ref.e_gpa, "GPa", f"E-Modul von {ref.name}")
    return v


def _trapz(y, x) -> float:
    return float(np.trapezoid(y, x)) if hasattr(np, "trapezoid") else float(np.trapz(y, x))


def measured_elongation_mm(r: "Result") -> np.ndarray | None:
    """Gemessene Verlängerung ΔL in mm im aktiven Abschnitt, wenn es sie gibt: nur bei Messungen aus einem Datensatz
    mit Weg- oder Dehnungsspalte (Weg in µm, Code 4). Der Weg einer .flps-Datei ist in keiner Einheit bestätigt."""
    o = r.device.get("origin") or {}
    if not ((o.get("roles") or {}).get("ext") and r.device.get("displacement_unit_code") == 4):
        return None
    return np.asarray(r.prep.displacement[:len(r.t)], dtype=float) / 1000.0


def work_to_break(r: "Result") -> tuple[float, str] | None:
    """Arbeit bis zum Bruch W = ∫ F dL in J, vom ersten Punkt bis zum Bruchpunkt (ohne Bruch: bis zum Ende).

    Mit gemessener Verlängerung (Datensatz mit Weg oder Dehnung) über deren Verlauf, sonst über den Traversenweg
    x = max(t − t0, 0)·v. Ohne beides: None."""
    end = r.break_idx if r.break_idx is not None else len(r.t) - 1
    sel = slice(0, end + 1)
    dl = measured_elongation_mm(r)
    if dl is not None:
        return _trapz(r.force[sel], dl[sel]) / 1000.0, "(aus der gemessenen Verlängerung, ∫F dL)"
    if r.v_mm_s:
        x = np.clip(r.t[sel] - r.t0, 0, None) * r.v_mm_s           # Weg in mm ab Kraftanstieg
        return _trapz(r.force[sel], x) / 1000.0, "(aus dem Traversenweg v·(t − t0))"
    return None


def evaluate_equations(defs, variables: dict, lang: str = "de") -> list:
    F = _labcalc()
    if F is None:
        return []
    return F.evaluate(defs, variables, lang=lang)


def material_label(r: Result) -> str:
    """Werkstoffangabe fuer Ausgaben: Freitext des Benutzers, sonst der gewaehlte Referenzwerkstoff."""
    if r.config.material:
        return r.config.material
    if r.reference is not None:
        return f"{r.reference.name} (Referenz, nicht gemessen)"
    return ""


def specimen_label(r: Result) -> str:
    c = r.config
    if c.specimen_mode == "manuell" or c.shape == MANUAL_SHAPE:
        base = "Manuell"
    else:
        base = c.shape
    if c.section == "rund":
        return f"{base}, rund d = {fmt(c.diameter_mm, 2, 'mm')}"
    if c.section == "rohr":
        return f"{base}, Rohr D = {fmt(c.outer_d_mm, 2, 'mm')}, t = {fmt(c.wall_mm, 2, 'mm')}"
    return f"{base}, b = {fmt(c.width_mm, 2, 'mm')}, Dicke {fmt(c.thickness_mm, 2, 'mm')}"


def _clean(o):
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, np.ndarray):
        return _clean(o.tolist())
    if isinstance(o, (np.floating,)):
        o = float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, float) and not math.isfinite(o):
        return None
    return o


def result_to_dict(r: Result, include_series: bool = True) -> dict:
    d = {
        "source": r.source, "name": r.name, "config": r.config.to_dict(), "device": r.device,
        "mode": r.mode, "unit": r.unit, "a0": r.a0, "a0_source": r.config.area_source(), "l0": r.l0,
        "v_mm_s": r.v_mm_s, "t0": r.t0, "window_points": r.window_points,
        "kv": r.kv, "warnings": r.warnings, "comparison": r.comparison,
        "yield_table": r.yield_table, "e_schein_gpa": r.e_schein_gpa,
        "group": r.group, "reference": r.ref_cmp, "shape_info": r.shape_info,
        "material_label": material_label(r),
        "extras": [a.name for a in r.extras],
        "equations": list(r.equations),
        "variables": [{"name": k, **v} for k, v in r.variables.items()],
    }
    if include_series:
        d["series"] = {
            "t": np.round(r.t, 4), "y": r.y, "F": r.force,
            "strain": r.strain if r.strain is not None else None,
            "phase": r.phases[:len(r.t)],
            "line": r.fit.k * r.t + r.fit.q,
        }
    return _clean(d)
