"""Werkzeuge des Moduls als Funktionen req -> Ergebnis (JSON-tauglich). Server und Bericht rufen dieselben auf."""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

_SDK = Path(__file__).resolve().parents[3] / "sdk" / "python"
if _SDK.is_dir() and str(_SDK) not in sys.path:
    sys.path.insert(0, str(_SDK))

import labtable  # noqa: E402

from . import corrcreep as CC  # noqa: E402
from . import cryst as C  # noqa: E402
from . import fatigue as FT  # noqa: E402
from . import gitter as GT  # noqa: E402
from . import hardness as HD  # noqa: E402
from . import laminate as LM  # noqa: E402
from . import phasediag as PD  # noqa: E402
from . import refs as RF  # noqa: E402
from . import reliability as RL  # noqa: E402
from . import select as SL  # noqa: E402
from . import steel as ST  # noqa: E402
from . import xrd as XR  # noqa: E402
from . import xrdio as IO  # noqa: E402

MAX_POINTS = 6000
TOOLS = ("auswahl", "karten", "kristall", "gitter", "xrd", "phasen", "stahl", "laminat", "ermuedung", "weibull", "bruch",
         "haerte", "korrosion", "kriechen")


class ToolError(ValueError):
    pass


ERRORS = (ToolError, C.CrystError, IO.XrdError, XR.XrdCalcError, PD.DiagramError, ST.SteelError, LM.LamError,
          FT.FatigueError, RL.RelError, HD.HardError, CC.CorrError, SL.SelError, GT.LatticeError)


class Ctx:
    """Zugriff auf die geladenen Dateien: {iid: {"kind", "name", "obj"}}."""

    def __init__(self, items: dict | None = None):
        self.items = items or {}

    def get(self, iid, kind=None):
        it = self.items.get(str(iid))
        if it is None:
            raise LookupError("Datei nicht geladen")
        if kind and it["kind"] != kind:
            raise ToolError(f"{it['name']} ist keine {kind}-Datei")
        return it

    def cif_phases(self) -> list[dict]:
        out = []
        for iid, it in self.items.items():
            if it["kind"] == "cif":
                out.append({**it["obj"], "id": "cif:" + iid, "own": True})
        return out

    def phases_all(self) -> list[dict]:
        return C.builtin_phases() + self.cif_phases()

    def phase(self, pid: str) -> dict:
        return C.phase(pid, self.cif_phases())


def _f(v, name: str, lo: float | None = None, hi: float | None = None, default=None) -> float:
    if v in (None, ""):
        if default is not None:
            return float(default)
        raise ToolError(f"{name} fehlt")
    try:
        x = float(v)
    except (TypeError, ValueError):
        raise ToolError(f"{name} ist keine Zahl") from None
    if not math.isfinite(x) or (lo is not None and x < lo) or (hi is not None and x > hi):
        raise ToolError(f"{name} = {x:g} ausserhalb des zulässigen Bereichs")
    return x


def thin(x, *ys, n: int = MAX_POINTS):
    """Für die Anzeige: höchstens n Punkte (Min/Max je Abschnitt, damit Spitzen sichtbar bleiben)."""
    x = np.asarray(x, float)
    if len(x) <= n:
        return [x.tolist()] + [np.asarray(y, float).tolist() for y in ys]
    B = n // 2
    edges = np.linspace(0, len(x), B + 1).astype(int)
    idx = []
    ref = np.asarray(ys[0], float)
    for a, b in zip(edges[:-1], edges[1:]):
        if b <= a:
            continue
        seg = ref[a:b]
        i0, i1 = a + int(np.argmin(seg)), a + int(np.argmax(seg))
        idx += sorted({i0, i1})
    idx = np.array(sorted(set(idx)))
    return [x[idx].tolist()] + [np.asarray(y, float)[idx].tolist() for y in ys]


# ----------------------------------------------------------------------------- Tabellen
def parse_table_text(text: str) -> dict:
    """Zahlentabelle aus Text: Spalten mit Namen und Einheit."""
    if not text or not text.strip():
        raise ToolError("Tabelle ist leer")
    lines = text.splitlines()
    sn = labtable.sniff(text)
    sep, dec = sn["sep"], sn["dec_comma"]
    if sn["end"] - sn["start"] < 1 or sn["ncol"] < 1:
        raise ToolError("Keine Zahlenspalten gefunden")
    head = labtable.split(lines[sn["header"]], sep) if sn["header"] is not None else []
    units = labtable.split(lines[sn["units"]], sep) if sn["units"] is not None else []
    cols = []
    rows = [labtable.split(ln, sep) for ln in lines[sn["start"]:sn["end"]]]
    for j in range(sn["ncol"]):
        name, unit = labtable.name_unit(head[j]) if j < len(head) else (f"Spalte {j + 1}", "")
        if j < len(units) and units[j].strip():
            unit = units[j].strip().strip("[]()")
        vals = []
        for r in rows:
            v = labtable.tofloat(r[j], dec) if j < len(r) else float("nan")
            vals.append(v if math.isfinite(v) else None)
        texts = [r[j] if j < len(r) else "" for r in rows]
        cols.append({"name": name or f"Spalte {j + 1}", "unit": unit, "values": vals, "text": texts})
    return {"columns": cols, "n": len(rows)}


def table(req: dict, ctx: Ctx) -> dict:
    if req.get("item"):
        it = ctx.get(req["item"], "table")
        return {**parse_table_text(it["obj"]), "name": it["name"]}
    return parse_table_text(req.get("text") or "")


# ----------------------------------------------------------------------------- Auswahl und Karten
def auswahl(req: dict, ctx: Ctx) -> dict:
    lang = req.get("lang", "de")
    px, py = req.get("x") or "rho", req.get("y") or "E"
    out = SL.chart(px, py, req.get("classes") or None, bool(req.get("mp")), lang)
    expo = req.get("expo")
    if req.get("index") in SL.INDICES and not expo:
        expo = SL.INDICES[req["index"]][2]
    own = _own_points(req.get("own") or [])
    if expo:
        expo = {k: float(v) for k, v in expo.items() if v not in (None, "", 0)}
        out["rank"] = SL.rank(expo, req.get("limits") or [], req.get("classes") or None, bool(req.get("mp")), lang)
        out["slope"] = SL.guide_slope(expo, px, py)
        out["expo"] = expo
        if own:
            _rank_own(out["rank"], own, expo, px, py, req.get("limits") or [], lang)
    out["own"] = own
    out["refs"] = RF.listing(SL.REFS + (["jain2013", "dejong2015"] if req.get("mp") else []), lang)
    return out


def _own_points(rows: list) -> list[dict]:
    """Eigene Punkte des Nutzers in den Anzeigeeinheiten der gewählten Achsen, je mit Quellenangabe (Freitext)."""
    out = []
    for k, p in enumerate(rows, 1):
        name = str(p.get("name") or "").strip()
        try:
            x, y = float(p.get("x")), float(p.get("y"))
        except (TypeError, ValueError):
            raise ToolError(f"Eigener Punkt {k}: x und y müssen Zahlen sein") from None
        if not name:
            raise ToolError(f"Eigener Punkt {k}: Name fehlt")
        if not (x > 0 and y > 0 and math.isfinite(x) and math.isfinite(y)):
            raise ToolError(f"Eigener Punkt {k} ({name}): x und y müssen positiv sein (logarithmische Achsen)")
        out.append({"id": f"own-{k}", "name": name, "x": x, "y": y, "src": str(p.get("src") or "").strip()})
    return out


def _rank_own(rank: dict, own: list[dict], expo: dict, px: str, py: str, limits: list, lang: str):
    """Eigene Punkte in die Rangliste: M nur, wenn die Kennzahl allein von den beiden Achsen abhängt."""
    de = lang == "de"
    for p in own:
        why = []
        if set(expo) - {px, py}:
            why.append("Kennzahl braucht weitere Eigenschaften" if de else "index needs further properties")
        val = {px: p["x"], py: p["y"]}
        for lim in limits:
            v = val.get(lim.get("prop"))
            if v is None:
                why.append(f"{lim.get('prop')} {'fehlt' if de else 'missing'}")
                continue
            if lim.get("min") not in (None, "") and v < float(lim["min"]):
                why.append(f"{lim['prop']} = {v:.4g} < {float(lim['min']):g}")
            if lim.get("max") not in (None, "") and v > float(lim["max"]):
                why.append(f"{lim['prop']} = {v:.4g} > {float(lim['max']):g}")
        M_ = None if why else math.prod(val[k] ** e for k, e in expo.items())
        row = {"id": p["id"], "name": p["name"], "klasse": "eigen", "M": M_, "why": why, "mp": False,
               "unchecked": False, "own": True, "src": p["src"]}
        (rank["excluded"] if why else rank["ranked"]).append(row)
    rank["ranked"].sort(key=lambda r: -r["M"])
    for i, r in enumerate(rank["ranked"], 1):
        r["rank"] = i
    rank["n_ok"] = len(rank["ranked"])
    rank["n_out"] = len(rank["excluded"])


def karten(req: dict, ctx: Ctx) -> dict:
    names = [n for n in (req.get("names") or []) if n]
    if not names:
        return {"cards": [], "rows": []}
    out = SL.compare(names, req.get("lang", "de"))
    return out


def suche(req: dict, ctx: Ctx) -> dict:
    from labcalc import materials as M
    return {"rows": M.search(req.get("q") or "", req.get("klasse") or None, req.get("prop") or None, 60,
                             req.get("lang", "de"))}


# ----------------------------------------------------------------------------- Kristall
def _lam(req) -> tuple[float, float | None, float]:
    tube = req.get("tube") or "Cu"
    if req.get("lam1"):
        return _f(req["lam1"], "λ", 0.1, 5), (float(req["lam2"]) if req.get("lam2") else None), float(req.get("ratio") or 0.5)
    if tube not in C.TUBES:
        raise ToolError(f"Röhre {tube} unbekannt")
    return C.TUBES[tube]


def kristall(req: dict, ctx: Ctx) -> dict:
    lam1, lam2, ratio = _lam(req)
    lang = req.get("lang", "de")
    if req.get("custom"):
        cu = req["custom"]
        p = {"id": "custom", "name": cu.get("name") or "Eigene Zelle", "system": cu.get("system", "cubic"),
             "cell": cu.get("cell") or {}, "centring": cu.get("centring", "P"), "atoms": cu.get("atoms") or [],
             "ops": cu.get("ops") or None}
        if not p["atoms"]:
            p["atoms"] = [{"el": cu.get("el") or "Fe", "x": 0, "y": 0, "z": 0}]
    else:
        p = ctx.phase(req.get("phase") or "cu")
    tmin, tmax = _f(req.get("tth_min"), "2θ min", 1, 170, 10), _f(req.get("tth_max"), "2θ max", 2, 175, 120)
    info = C.phase_info(p, lam1, lang)
    info["lines"] = [L for L in info["lines"] if tmin <= L["tth"] <= tmax]
    fw = _f(req.get("fwhm"), "FWHM", 0.005, 5, 0.1)
    if req.get("profile", True):
        x = np.arange(tmin, tmax, max(fw / 8, 0.005))
        y = C.profile(info["lines"], x, fw, 0.5, (lam1, lam2, ratio) if (lam2 and req.get("ka2", True)) else None)
        info["profile"] = {"x": x.tolist(), "y": y.tolist()}
    hkl = req.get("hkl")
    cell = C.Cell.of(p["cell"], p.get("system"))
    if hkl:
        h = [int(v) for v in hkl]
        if any(h):
            d = float(cell.d(h))
            info["plane"] = {"hkl": h, "d": d, "tth": float(C.bragg_2theta(d, lam1))}
    uvw = req.get("uvw")
    if uvw and any(int(v) for v in uvw):
        u = np.array([int(v) for v in uvw], float)
        info["direction"] = {"uvw": [int(v) for v in uvw], "length": float(math.sqrt(u @ cell.G @ u))}
    if req.get("hkl2") and hkl:
        info["angle_planes"] = cell.angle_hkl(hkl, req["hkl2"])
    info["lam"] = [lam1, lam2, ratio]
    info["refs"] = RF.listing(C.REFS + [p.get("q")] if p.get("q") else C.REFS, lang)
    return info


def phasen_liste(req: dict, ctx: Ctx) -> dict:
    lang = req.get("lang", "de")
    return {"phases": [{"id": p["id"], "name": (p.get("name_en") if lang == "en" and p.get("name_en") else p.get("name")),
                        "formula": p.get("formula", ""), "system": p.get("system", ""), "own": bool(p.get("own"))}
                       for p in ctx.phases_all()]}


# ----------------------------------------------------------------------------- XRD
def xrd(req: dict, ctx: Ctx) -> dict:
    it = ctx.get(req.get("item"), "xrd")
    pat = it["obj"]
    opt = dict(req.get("opt") or {})
    tube = req.get("tube") or "file"
    if req.get("lam1"):
        opt.update(lam1=_f(req["lam1"], "λ", 0.1, 5), lam2=float(req["lam2"]) if req.get("lam2") else None,
                   ratio=float(req.get("ratio") or 0.5))
    elif tube != "file":
        if tube not in C.TUBES:
            raise ToolError(f"Röhre {tube} unbekannt")
        opt["lam1"], opt["lam2"], opt["ratio"] = C.TUBES[tube]
        if req.get("mono"):
            opt["lam2"] = None
    res = XR.analyse(pat, opt, ctx.phases_all())
    x, y, bg, net = thin(pat.tth, res.pop("y"), res.pop("bg"), res.pop("net"))
    res["curve"] = {"x": x, "y": y, "bg": bg, "net": net}
    res["raw"] = thin(pat.tth, pat.counts)[1] if len(pat.tth) > MAX_POINTS else pat.counts.tolist()
    res["meta"] = pat.describe()
    sticks = []
    for pid in opt.get("overlay") or []:
        try:
            ph = ctx.phase(pid)
        except C.CrystError:
            continue
        lines = C.reflections(ph, res["lam1"], max(pat.tth[0], 1), min(pat.tth[-1], 175))
        sticks.append({"id": pid, "name": ph.get("name"), "lines": [{"tth": L["tth"], "I": L["Irel"], "hkl": L["hkl"]} for L in lines]})
    res["sticks"] = sticks
    keys = set()
    for k in ("smooth", "background", "peaks", "scherrer", "wh", "nelson", "match", "quant", "kalpha2"):
        keys.update(XR.REFS.get(k, []))
    res["refs"] = RF.listing(sorted(keys), req.get("lang", "de"))
    return res


# ----------------------------------------------------------------------------- Phasendiagramme
def phasen(req: dict, ctx: Ctx) -> dict:
    lang = req.get("lang", "de")
    sid = req.get("system") or "fe-c"
    out: dict = {"systems": PD.systems(lang)}
    if req.get("model"):
        p = {**PD.preset("cu-ni"), **{k: v for k, v in req["model"].items() if v not in (None, "")}}
        for k in ("TmA", "TmB", "HA", "HB", "omega_L", "omega_S", "MA", "MB"):
            p[k] = float(p[k])
        p["Tlim"] = [float(v) for v in (req["model"].get("Tlim") or p.get("Tlim") or [p["TmA"] - 400, max(p["TmA"], p["TmB"]) + 50])]
        unit = req.get("unit") or "wt"
        out["computed"] = PD.computed_diagram(p, int(req.get("nT") or 121), 801, unit)
        out["model"] = p
        if req.get("x") not in (None, "") and req.get("T") not in (None, ""):
            out["lever"] = PD.lever_computed(p, _f(req["x"], "x", 0, 100), _f(req["T"], "T"), unit)
        out["refs"] = RF.listing(PD.REFS_MODEL + list(p.get("q") or []), lang)
        return out
    s = PD.system(sid)
    out["diagram"] = {k: s[k] for k in ("id", "A", "B", "xlim", "Tlim", "regions", "invariants", "points", "q")}
    out["diagram"]["name"] = s.get("name_en") if lang == "en" else s["name"]
    out["diagram"]["x_label"] = s.get("x_label_en") if lang == "en" else s["x_label"]
    if req.get("x") not in (None, ""):
        x = _f(req["x"], "Zusammensetzung", *s["xlim"])
        if req.get("T") not in (None, ""):
            out["lever"] = PD.lever(s, x, _f(req["T"], "Temperatur"), lang)
        out["constituents"] = PD.constituents(s, x, lang)
        out["cooling"] = PD.cooling(s, x, 1.0, lang)
    out["refs"] = RF.listing(PD.REFS + s["q"], lang)
    return out


# ----------------------------------------------------------------------------- Stahl
def stahl(req: dict, ctx: Ctx) -> dict:
    out = ST.composition_report(req.get("comp") or {}, req.get("preheat") or None)
    hj = req.get("hj") or {}
    if hj.get("T1") not in (None, "") and hj.get("t1") not in (None, ""):
        C_ = _f(hj.get("C"), "C", 5, 40, 20)
        out["hj"] = ST.hollomon_jaffe(_f(hj["T1"], "T₁"), _f(hj["t1"], "t₁", 1e-6), None, C_)
        if hj.get("T2") not in (None, ""):
            out["hj"]["equiv"] = ST.equivalent_tempering(float(hj["T1"]), float(hj["t1"]), _f(hj["T2"], "T₂"), C_)
    cb = req.get("carb") or {}
    if cb.get("T") not in (None, "") and cb.get("t") not in (None, ""):
        out["carb"] = ST.carburise_profile(_f(cb.get("c0"), "c₀", 0, 2, 0.2), _f(cb.get("cs"), "c_s", 0, 2.5, 0.9),
                                           _f(cb["T"], "T", 700, 1200), _f(cb["t"], "t", 1e-3, 1000),
                                           float(cb["D0"]) if cb.get("D0") not in (None, "") else None,
                                           float(cb["Q"]) if cb.get("Q") not in (None, "") else None,
                                           _f(cb.get("limit"), "Grenzgehalt", 0, 2.5, 0.4),
                                           float(cb["depth"]) if cb.get("depth") not in (None, "") else None)
    keys = set()
    for v in ST.REFS.values():
        keys.update(v)
    out["refs"] = RF.listing(sorted(keys), req.get("lang", "de"))
    return out


# ----------------------------------------------------------------------------- Laminat
def laminat(req: dict, ctx: Ctx) -> dict:
    ply = dict(req.get("ply") or {})
    if req.get("material"):
        base = LM.ply_from_material(req["material"])
        ply = {**{k: v for k, v in base.items() if k not in ("src", "name")}, **{k: v for k, v in ply.items() if v not in (None, "")}}
        src = base
    else:
        src = None
    angles = LM.parse_layup(req.get("layup") or "[0/90]s")
    t = _f(req.get("t"), "Schichtdicke", 1e-4, 100, 0.125)
    N = [float(req.get(k) or 0) for k in ("Nx", "Ny", "Nxy")]
    Mm = [float(req.get(k) or 0) for k in ("Mx", "My", "Mxy")]
    out = LM.analyse(ply, angles, t, N, Mm, float(req.get("F12") if req.get("F12") not in (None, "") else -0.5),
                     float(req["ST"]) if req.get("ST") not in (None, "") else None)
    out["ply"] = ply
    out["material"] = src
    keys = set()
    for v in LM.REFS.values():
        keys.update(v)
    if src:
        keys.update(s["key"] for s in src["src"].values() if s.get("key"))
    out["refs"] = RF.listing(sorted(keys), req.get("lang", "de"))
    return out


# ----------------------------------------------------------------------------- Ermüdung
def _rows(req, *names):
    rows = req.get("rows") or []
    out = []
    for r in rows:
        try:
            out.append([float(r[n]) if r.get(n) not in (None, "") else None for n in names] + [r])
        except (TypeError, ValueError):
            raise ToolError("Tabelle enthält Text, wo Zahlen erwartet werden") from None
    return out


def ermuedung(req: dict, ctx: Ctx) -> dict:
    lang = req.get("lang", "de")
    out: dict = {}
    rows = [r for r in _rows(req, "sa", "sm", "N") if r[0] is not None and r[2] is not None]
    mat = req.get("mat") or {}
    Rm = float(mat["Rm"]) if mat.get("Rm") not in (None, "") else None
    Re = float(mat["Re"]) if mat.get("Re") not in (None, "") else None
    model = req.get("model") or "none"
    sf_hint = float(mat["sigma_f"]) if mat.get("sigma_f") not in (None, "") else None
    if rows:
        sar, notes = [], []
        for sa, sm, _N, r in rows:
            v = FT.equivalent(sa, sm or 0.0, model, Rm, Re, sf_hint) if (sm or model == "swt") else sa
            if v is None:
                notes.append(f"σa = {sa:g}, σm = {sm or 0:g}: Modell {model} nicht anwendbar, Punkt ausgelassen")
            sar.append(v)
        keep = [i for i, v in enumerate(sar) if v is not None]
        fit = FT.basquin_fit([sar[i] for i in keep], [rows[i][2] for i in keep],
                             [bool(rows[i][3].get("runout")) for i in keep])
        out["fit"] = fit
        best = fit.get("mle") or fit["lsq"]
        grid = np.logspace(math.log10(min(sar[i] for i in keep) * 0.8), math.log10(max(sar[i] for i in keep) * 1.2), 60)
        if fit["lsq_fit"].get("s"):
            out["band"] = FT.band(fit["lsq_fit"], grid)
        out["points"] = [{"sar": sar[i], "N": rows[i][2], "runout": bool(rows[i][3].get("runout")), "sa": rows[i][0],
                          "sm": rows[i][1]} for i in keep]
        out["line"] = {"sa": grid.tolist(), "N": [FT.life(s, best) for s in grid]}
        out["notes"] = notes
        if req.get("N_target"):
            Nt = float(req["N_target"])
            out["S_at_N"] = 10 ** ((math.log10(Nt) - best["A"]) / best["B"])
    mr = req.get("marin") or {}
    if mr.get("Rm") not in (None, ""):
        out["marin"] = FT.marin(_f(mr["Rm"], "Rm", 1, 5000), mr.get("surface") or "bearbeitet",
                                float(mr["d"]) if mr.get("d") not in (None, "") else None, mr.get("loading") or "biegung",
                                True, _f(mr.get("kd"), "kd", 0, 2, 1), _f(mr.get("rel"), "Zuverlässigkeit", 50, 99.999, 50),
                                float(mr["Se_prime"]) if mr.get("Se_prime") not in (None, "") else None)
    Se = None
    if req.get("Se") not in (None, ""):
        Se = _f(req["Se"], "Se", 0)
    elif out.get("marin"):
        Se = out["marin"]["Se"]
    if Se and (Rm or Re):
        out["haigh"] = FT.haigh(Se, Rm, Re)
        out["haigh_Se"] = Se
    ser = req.get("series")
    if ser:
        vals = [float(v) for v in ser if v not in (None, "")]
        cyc = FT.rainflow(vals, float(req.get("hyst") or 0))
        out["rainflow"] = {"n_rev": len(FT.reversals(vals, float(req.get("hyst") or 0))), "cycles": cyc[:5000],
                           "n_cycles": sum(c["count"] for c in cyc)}
        if out.get("fit"):
            best = out["fit"].get("mle") or out["fit"]["lsq"]
            out["miner"] = FT.miner(cyc, best, req.get("miner_model") or model, Rm, Re,
                                    Se if req.get("miner_cutoff") else None, float(req.get("repeats") or 1))
            out["miner"]["rows"] = out["miner"]["rows"][:2000]
    keys = set(FT.REFS["sn"])
    if rows and any(r[3].get("runout") for r in rows):
        keys.update(FT.REFS["mle"])
    if model in ("goodman", "gerber", "soderberg", "morrow"):
        keys.update(FT.REFS["mean"])
    if model == "swt":
        keys.update(FT.REFS["swt"])
    if out.get("marin"):
        keys.update(FT.REFS["marin"])
    if ser:
        keys.update(FT.REFS["rainflow"] + FT.REFS["miner"])
    out["refs"] = RF.listing(sorted(keys), lang)
    return out


# ----------------------------------------------------------------------------- Weibull, Bruch
def weibull(req: dict, ctx: Ctx) -> dict:
    vals = [float(v) for v in (req.get("values") or []) if v not in (None, "")]
    out = {"lsq": RL.weibull_lsq(vals), "mle": RL.weibull_mle(vals)}
    meth = req.get("method") or "mle"
    best = out[meth]
    if req.get("boot", True):
        out["boot"] = RL.bootstrap(vals, meth, int(req.get("B") or 1000), int(req.get("seed") or 20261118),
                                   float(req.get("level") or 0.9))
    out["method"] = meth
    out["q"] = {P: RL.quantile(best["m"], best["sigma0"], P) for P in (0.01, 0.05, 0.1, 0.5)}
    sz = req.get("size") or {}
    if sz.get("V1") not in (None, "") and sz.get("V2") not in (None, ""):
        m = best["m"]
        V1 = RL.v_eff(sz.get("kind1") or "zug", float(sz["V1"]), m, sz.get("Li1") and float(sz["Li1"]), sz.get("L1") and float(sz["L1"]))
        V2 = RL.v_eff(sz.get("kind2") or "zug", float(sz["V2"]), m, sz.get("Li2") and float(sz["Li2"]), sz.get("L2") and float(sz["L2"]))
        out["size"] = {"Veff1": V1, "Veff2": V2, "sigma2": RL.size_scale(best["sigma0"], m, V1, V2)}
    keys = set(RL.REFS["weibull"] + RL.REFS["ranks"] + (RL.REFS["mle"] if meth == "mle" else []))
    if out.get("boot"):
        keys.update(RL.REFS["boot"])
    if out.get("size"):
        keys.update(RL.REFS["size"])
    out["refs"] = RF.listing(sorted(keys), req.get("lang", "de"))
    return out


def bruch(req: dict, ctx: Ctx) -> dict:
    out = {}
    k = req.get("kq") or {}
    if k.get("P") not in (None, ""):
        out["kq"] = RL.k_q(k.get("geom") or "senb", _f(k["P"], "P_Q", 0), _f(k.get("B"), "B", 0), _f(k.get("W"), "W", 0),
                           _f(k.get("a"), "a", 0), float(k["S"]) if k.get("S") not in (None, "") else None,
                           float(k["Rp"]) if k.get("Rp") not in (None, "") else None,
                           float(k["Pmax"]) if k.get("Pmax") not in (None, "") else None)
    c = req.get("crack") or {}
    if c.get("KIc") not in (None, "") and c.get("sigma") not in (None, ""):
        out["crack"] = RL.critical_crack(_f(c["KIc"], "K_Ic", 0), _f(c["sigma"], "σ", 0), _f(c.get("Y"), "Y", 0, 10, 1))
        sig = np.linspace(0.2, 2.0, 60) * float(c["sigma"])
        out["crack"]["curve"] = {"sigma": sig.tolist(), "a_mm": [(float(c["KIc"]) / (float(c.get("Y") or 1) * s)) ** 2 / math.pi * 1e3 for s in sig]}
    out["refs"] = RF.listing(sorted(set(RL.REFS["e399"] + RL.REFS["crack"])), req.get("lang", "de"))
    return out


# ----------------------------------------------------------------------------- Härte
def haerte(req: dict, ctx: Ctx) -> dict:
    meth = req.get("method") or "HV"
    rows = req.get("indents") or []
    res = []
    for r in rows:
        try:
            F = _f(r.get("F"), "F", 0)
            if meth == "HV":
                v = HD.vickers(F, _f(r.get("d1"), "d1", 0), float(r["d2"]) if r.get("d2") not in (None, "") else None)
            elif meth == "HBW":
                v = HD.brinell(F, _f(r.get("D") or req.get("D"), "D", 0), _f(r.get("d1"), "d1", 0),
                               float(r["d2"]) if r.get("d2") not in (None, "") else None)
            elif meth == "HK":
                v = HD.knoop(F, _f(r.get("d1"), "d", 0))
            else:
                raise ToolError(f"Verfahren {meth} unbekannt")
            res.append({**v, "row": r})
        except (ToolError, HD.HardError) as e:
            res.append({"error": str(e), "row": r})
    vals = [x["value"] for x in res if "value" in x]
    out = {"method": meth, "rows": res}
    if vals:
        out["stats"] = HD.series(vals)
        conv = req.get("convert") or {}
        if conv.get("table"):
            tb = HD.parse_table(ctx.get(conv["table"], "hardtable")["obj"])
            out["table"] = {"scales": tb["scales"], "source": tb["source"], "n": tb["n"],
                            "name": ctx.get(conv["table"])["name"]}
            if conv.get("to"):
                out["converted"] = HD.convert(tb, out["stats"]["mean"], conv.get("from") or meth, conv["to"])
        elif meth == "HV":
            out["rule"] = HD.rule_of_thumb_Rm(out["stats"]["mean"])
    g = req.get("grain") or {}
    if g.get("L") not in (None, "") and g.get("N") not in (None, ""):
        out["grain"] = HD.grain_intercept(_f(g["L"], "Linienlänge", 0), _f(g["N"], "Schnittpunkte", 0), _f(g.get("M"), "Vergrösserung", 0, None, 1))
    elif g.get("NA") not in (None, ""):
        out["grain"] = HD.grain_planimetric(_f(g["NA"], "N_A", 0))
    hp = [r for r in (req.get("hp") or []) if r.get("d") not in (None, "") and r.get("s") not in (None, "")]
    if len(hp) >= 2:
        out["hp"] = HD.hall_petch([float(r["d"]) for r in hp], [float(r["s"]) for r in hp])
    keys = set(HD.REFS.get(meth, []))
    if out.get("rule"):
        keys.update(HD.REFS["rule"])
    if out.get("grain"):
        keys.update(HD.REFS["e112"])
    if out.get("hp"):
        keys.update(HD.REFS["hp"])
    out["refs"] = RF.listing(sorted(keys), req.get("lang", "de"))
    return out


# ----------------------------------------------------------------------------- Korrosion, Kriechen
def korrosion(req: dict, ctx: Ctx) -> dict:
    E = req.get("E") or []
    i = req.get("i") or []
    if req.get("item"):
        tb = table({"item": req["item"]}, ctx)
        ce, ci = int(req.get("colE") or 0), int(req.get("colI") or 1)
        E = tb["columns"][ce]["values"]
        i = tb["columns"][ci]["values"]
    E = np.array([float(v) if v is not None else np.nan for v in E])
    i = np.array([float(v) if v is not None else np.nan for v in i])
    escale = {"V": 1, "mV": 1e-3}.get(req.get("Eunit") or "V", 1)
    out = CC.tafel(E * escale, i, req.get("iunit") or "A", _f(req.get("area"), "Fläche", 0, None, 1),
                   _f(req.get("eta_min"), "η min", 0, 1, 0.05), _f(req.get("eta_max"), "η max", 0, 2, 0.15),
                   float(req["Ecorr"]) if req.get("Ecorr") not in (None, "") else None, bool(req.get("bv")),
                   _f(req.get("eta_fit"), "η Butler–Volmer", 0.002, 0.5, 0.02))
    x, y = thin(out.pop("E"), out.pop("j"))
    out["curve"] = {"E": x, "j": y}
    EW, rho = req.get("EW"), req.get("rho")
    if req.get("metal"):
        m = CC.equivalent_weight(req["metal"])
        EW, rho = EW or m["EW"], rho or m["rho"]
        out["metal"] = m
    if EW and rho:
        out["rate"] = CC.corrosion_rate(out["icorr"], float(EW), float(rho))
        out["EW"], out["rho"] = float(EW), float(rho)
    keys = set(CC.REFS["tafel"] + (CC.REFS["rp"] if out.get("Rp") else []) + (CC.REFS["rate"] if out.get("rate") else []))
    out["refs"] = RF.listing(sorted(keys), req.get("lang", "de"))
    return out


def kriechen(req: dict, ctx: Ctx) -> dict:
    out = {}
    rows = [r for r in (req.get("rows") or []) if r.get("s") not in (None, "") and r.get("T") not in (None, "")]
    lmp_rows = [r for r in rows if r.get("t") not in (None, "")]
    if len(lmp_rows) >= 3:
        Cv = None if req.get("fitC") else _f(req.get("C"), "C", 1, 60, 20)
        fit = CC.lmp_fit([float(r["s"]) for r in lmp_rows], [float(r["T"]) for r in lmp_rows],
                         [float(r["t"]) for r in lmp_rows], Cv, int(req.get("deg") or 2))
        P = np.linspace(min(fit["P"]), max(fit["P"]), 80)
        fit["curve"] = {"P": P.tolist(), "sigma": (10 ** np.polyval(fit["coef"], P / 1e3)).tolist()}
        out["lmp"] = fit
        pr = req.get("predict") or {}
        if pr.get("s") not in (None, "") and pr.get("T") not in (None, ""):
            out["predict"] = CC.lmp_predict(fit, _f(pr["s"], "σ", 0), _f(pr["T"], "T"))
    nr = [r for r in rows if r.get("rate") not in (None, "")]
    if len(nr) >= 2:
        out["norton"] = CC.norton_fit([float(r["rate"]) for r in nr], [float(r["s"]) for r in nr],
                                      [float(r["T"]) for r in nr])
        out["norton"]["points"] = [{"s": float(r["s"]), "T": float(r["T"]), "rate": float(r["rate"])} for r in nr]
    keys = set((CC.REFS["lmp"] if out.get("lmp") else []) + (CC.REFS["norton"] if out.get("norton") else []))
    out["refs"] = RF.listing(sorted(keys), req.get("lang", "de"))
    return out


def gitter(req: dict, ctx: Ctx) -> dict:
    """KG: Gitterausschnitt eines Werkstoffs bei T (gitter.build) mit den Quellen als Liste."""
    lang = req.get("lang", "de")
    out = GT.build(req, lang)
    out["refs"] = RF.listing(out["refs"], lang)
    return out


DISPATCH = {"auswahl": auswahl, "karten": karten, "suche": suche, "kristall": kristall, "gitter": gitter, "phasen_liste": phasen_liste,
            "xrd": xrd, "phasen": phasen, "stahl": stahl, "laminat": laminat, "ermuedung": ermuedung,
            "weibull": weibull, "bruch": bruch, "haerte": haerte, "korrosion": korrosion, "kriechen": kriechen,
            "table": table}


def run(name: str, req: dict, ctx: Ctx) -> dict:
    fn = DISPATCH.get(name)
    if fn is None:
        raise LookupError(f"Werkzeug „{name}“ unbekannt")
    return fn(req or {}, ctx)
