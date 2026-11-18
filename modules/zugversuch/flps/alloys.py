"""Vergleichswerkstoffe (Spezifikation Abschnitt 5). Laedt data/alloys.json.

Die Datei enthaelt neben den Aluminiumlegierungen der Spezifikation weitere Werkstoffklassen
(Stahl, Kunststoffe, Elastomere, ...). Verglichen wird immer innerhalb einer gewaehlten
Vergleichsgruppe; Voreinstellung ist Aluminium wie in der Spezifikation.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "alloys.json"

# Grenzen der Einordnung (relative Abweichungen)
RM_CANDIDATE_TOL = 0.15     # Rm innerhalb +-15 %  -> Kandidat
RATIO_TOL = 0.15            # Verfestigungsverhaeltnis innerhalb +-15 %
RM_EXCLUDE_TOL = 0.40       # Rm mehr als 40 % daneben -> ausgeschlossen

METALS = ["Stahl", "Edelstahl", "Gusseisen", "Aluminium", "Kupfer", "Titan", "Magnesium", "Nickel"]
DEFAULT_GROUP = "Aluminium"
GROUP_ALL_METALS = "alle Metalle"
GROUP_ALL = "alle Werkstoffe"


@dataclass
class Alloy:
    name: str
    rp: float | None  # Rp0,2 bzw. Streckspannung [MPa], None wenn nicht definiert
    rm: float         # Rm [MPa]
    a_pct: float      # Bruchdehnung A [%]
    e_gpa: float      # E [GPa]
    rm_min: float | None
    rm_max: float | None
    source: str
    category: str = "Aluminium"
    basis: str = ""
    url: str = ""        # Fundstelle der Quelle (Datenblatt, Norm-Bezugsquelle, Institut)
    year: str = ""       # Jahr bzw. Ausgabe der Quelle
    accessed: str = ""   # Abrufdatum der URL (JJJJ-MM-TT)
    own: bool = False    # eigener Werkstoff der Nutzerin (eigene_werkstoffe.json)
    cite: dict | None = None    # strukturierte Quelle (labcite), sonst gilt der Freitext source
    curve: list | None = None   # eigene Kurve [[Dehnung %, Spannung MPa], ...] statt der idealisierten
    oid: str = ""        # id im Speicher der eigenen Werkstoffe

    @property
    def ratio(self) -> float | None:
        return self.rm / self.rp if self.rp else None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["ratio"] = self.ratio
        return d


# --- Eigene Werkstoffe --------------------------------------------------------------
OWN_CATEGORY = "Eigene Werkstoffe"


def _num(v, what: str, required: bool = True, positive: bool = True):
    if v is None or (isinstance(v, str) and not v.strip()):
        if required:
            raise ValueError(f"{what} fehlt")
        return None
    try:
        f = float(str(v).strip().replace(",", "."))
    except ValueError:
        raise ValueError(f"{what}: keine Zahl ({v})") from None
    if not math.isfinite(f) or (positive and f <= 0):
        raise ValueError(f"{what} muss eine positive Zahl sein")
    return f


def parse_curve(text_or_list) -> list | None:
    """Eigene Kurve aus Text (zwei Spalten Dehnung % und Spannung MPa; Trenner Tab, Semikolon, Leerzeichen oder Komma
    bei Dezimalpunkt) oder aus einer Liste von Paaren. Sortiert, Dehnung streng steigend, Start bei 0."""
    if not text_or_list:
        return None
    pts = []
    if isinstance(text_or_list, str):
        for line in text_or_list.splitlines():
            line = line.strip()
            if not line or line[0] in "#%;":
                continue
            if ";" in line or "\t" in line:
                parts = [p.strip().replace(",", ".") for p in line.replace("\t", ";").split(";")]
            elif line.count(",") == 1 and " " not in line:
                parts = line.split(",")
            else:
                parts = [p.replace(",", ".") for p in line.split()]
            parts = [p for p in parts if p]
            if len(parts) < 2:
                continue
            try:
                pts.append((float(parts[0]), float(parts[1])))
            except ValueError:
                continue   # Kopfzeile
    else:
        for p in text_or_list:
            pts.append((float(p[0]), float(p[1])))
    pts = [(e, s) for e, s in pts if math.isfinite(e) and math.isfinite(s) and e >= 0]
    pts.sort()
    out = []
    for e, s in pts:
        if out and e <= out[-1][0]:
            continue
        out.append([e, s])
    if len(out) < 3:
        raise ValueError("Kurve: mindestens drei Punkte (Dehnung in %, Spannung in MPa) nötig")
    if len(out) > 5000:
        raise ValueError("Kurve: höchstens 5000 Punkte")
    if out[0][0] > 0:
        out.insert(0, [0.0, 0.0])
    return out


def own_from_dict(d: dict) -> Alloy:
    """Eigenen Werkstoff prüfen und als Alloy anlegen. Mit Kurve sind Rm, A und E optional (aus der Kurve)."""
    name = str(d.get("name") or "").strip()
    if not name:
        raise ValueError("Name fehlt")
    if len(name) > 80:
        raise ValueError("Name: höchstens 80 Zeichen")
    curve = parse_curve(d.get("curve")) if d.get("curve") else None
    if curve:
        c = np.asarray(curve)
        rm = _num(d.get("rm"), "Rm", required=False) or float(c[:, 1].max())
        a_pct = _num(d.get("a_pct"), "A", required=False) or float(c[-1, 0])
        e = _num(d.get("e_gpa"), "E", required=False)
        if e is None:  # Anfangssteigung bis 30 % von Rm (Sekante), nur als Näherung für die Anzeige
            k = np.where(c[:, 1] <= 0.3 * c[:, 1].max())[0]
            k = k[k > 0]
            i = int(k[-1]) if len(k) else 1
            e = max(1e-6, (c[i, 1] - c[0, 1]) / max(c[i, 0] - c[0, 0], 1e-9) * 100 / 1000)
    else:
        rm = _num(d.get("rm"), "Rm")
        a_pct = _num(d.get("a_pct"), "Bruchdehnung A")
        e = _num(d.get("e_gpa"), "E-Modul")
    rp = _num(d.get("rp"), "Rp0,2", required=False)
    if rp is not None and rp > rm:
        raise ValueError("Rp0,2 ist grösser als Rm")
    lo = _num(d.get("rm_min"), "Rm min", required=False)
    hi = _num(d.get("rm_max"), "Rm max", required=False)
    if lo is not None and hi is not None and lo > hi:
        raise ValueError("Rm min ist grösser als Rm max")
    cite = d.get("cite") if isinstance(d.get("cite"), dict) and d.get("cite") else None
    src = str(d.get("source") or "").strip()
    if cite and not src:
        try:
            import labcite
            src = labcite.text(cite)
        except ImportError:
            src = cite.get("title", "")
    return Alloy(name=name, rp=rp, rm=rm, a_pct=a_pct, e_gpa=e, rm_min=lo, rm_max=hi, source=src,
                 category=str(d.get("category") or OWN_CATEGORY).strip()[:40] or OWN_CATEGORY,
                 basis=str(d.get("basis") or "").strip()[:200], url=str((cite or {}).get("url") or d.get("url") or ""),
                 year=str((cite or {}).get("year") or d.get("year") or ""), accessed=str((cite or {}).get("accessed") or ""),
                 own=True, cite=cite, curve=curve, oid=str(d.get("id") or ""))


def merge_own(builtin: list[Alloy], own_rows: list[dict], strict: bool = False) -> tuple[list[Alloy], list[str]]:
    """Eingebaute und eigene Werkstoffe zusammenführen. Ein eigener Name, der schon eingebaut ist, wird übersprungen
    (die Schlüssel der Literaturangaben hängen am Namen). Gibt (Liste, Fehlermeldungen) zurück."""
    out, errs = list(builtin), []
    names = {a.name for a in builtin}
    for d in own_rows:
        try:
            a = own_from_dict(d)
        except ValueError as e:
            errs.append(f"{d.get('name') or '?'}: {e}")
            continue
        if a.name in names:
            errs.append(f"{a.name}: Name ist schon vergeben")
            continue
        names.add(a.name)
        out.append(a)
    if strict and errs:
        raise ValueError("; ".join(errs))
    return out, errs


def load_alloys(path: str | Path | None = None) -> list[Alloy]:
    p = Path(path) if path else DEFAULT_PATH
    raw = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        rows = raw.get("werkstoffe") or raw.get("alloys") or []
    else:
        rows = raw
    out = []
    for r in rows:
        rp = r.get("Rp02_MPa")
        out.append(Alloy(
            name=r["name"], rp=float(rp) if rp is not None else None, rm=float(r["Rm_MPa"]),
            a_pct=float(r["A_pct"]), e_gpa=float(r["E_GPa"]),
            rm_min=r.get("Rm_min"), rm_max=r.get("Rm_max"), source=r.get("quelle", ""),
            category=r.get("kategorie", "Aluminium"), basis=r.get("basis", ""),
            url=r.get("url", "") or "", year=str(r.get("jahr") or ""), accessed=r.get("abgerufen", "") or "",
        ))
    return out


def categories(alloys: list[Alloy]) -> list[str]:
    seen: list[str] = []
    for a in alloys:
        if a.category not in seen:
            seen.append(a.category)
    return seen


def groups(alloys: list[Alloy]) -> list[str]:
    return categories(alloys) + [GROUP_ALL_METALS, GROUP_ALL]


def select_group(alloys: list[Alloy], group: str | None) -> list[Alloy]:
    """Werkstoffe einer Vergleichsgruppe. Unbekannte oder leere Gruppe -> Aluminium."""
    g = group or DEFAULT_GROUP
    if g == GROUP_ALL:
        return list(alloys)
    if g == GROUP_ALL_METALS:
        return [a for a in alloys if a.category in METALS]
    sel = [a for a in alloys if a.category == g]
    return sel or [a for a in alloys if a.category == DEFAULT_GROUP] or list(alloys)


def find(alloys: list[Alloy], name: str | None) -> Alloy | None:
    if not name:
        return None
    return next((a for a in alloys if a.name == name), None)


# --- 5.2 Idealisierte Kurve ------------------------------------------------------
def ideal_curve(a: Alloy, eps: np.ndarray) -> np.ndarray:
    """sigma(eps) in MPa, eps dimensionslos. Ausserhalb 0..A ist der Wert NaN.

    Modell der Spezifikation fuer Werkstoffe mit Rp. Ohne Rp (sproede Werkstoffe, Elastomere,
    Papier, Holz, Faserverbund) linear bis Rm bei A. Hat der Werkstoff eine eigene Kurve (aus einer Quelle
    digitalisiert oder gemessen), wird sie linear interpoliert statt idealisiert.
    """
    if a.curve:
        c = np.asarray(a.curve, dtype=float)
        eps = np.asarray(eps, dtype=float)
        x = eps * 100.0
        s = np.interp(x, c[:, 0], c[:, 1])
        return np.where((x >= 0) & (x <= c[-1, 0]), s, np.nan)
    E = a.e_gpa * 1000.0
    Rm, A = a.rm, a.a_pct / 100.0
    eps = np.asarray(eps, dtype=float)
    s = np.full_like(eps, np.nan)
    if not a.rp:
        m = (eps >= 0) & (eps <= A)
        s[m] = Rm * eps[m] / A
        return s
    Rp = a.rp
    ey = Rp / E + 0.002
    ag = 0.55 * A
    if ey >= A:  # sehr kleine Bruchdehnung: linear bis Rm
        m = (eps >= 0) & (eps <= A)
        s[m] = Rm * eps[m] / A
        return s
    if ag <= ey:  # Gleichmassdehnung liegt vor dem elastischen Ende
        ag = 0.5 * (ey + A)
    m1 = (eps >= 0) & (eps <= ey)
    s[m1] = Rp * eps[m1] / ey
    m2 = (eps > ey) & (eps <= ag)
    s[m2] = Rp + (Rm - Rp) * ((eps[m2] - ey) / (ag - ey)) ** 0.45
    m3 = (eps > ag) & (eps <= A)
    s[m3] = Rm - 0.07 * Rm * (eps[m3] - ag) / (A - ag)
    return s


# --- 5.3 Huellkurve --------------------------------------------------------------
def envelope(alloys: list[Alloy], n: int = 1500, eps_max: float | None = None):
    """Gemeinsames Dehnungsraster, punktweise Max und Min ueber alle Werkstoffe der Liste,
    die bei dieser Dehnung noch nicht gebrochen sind. Spruenge werden nicht geglaettet."""
    if eps_max is None:
        eps_max = max(max(a.a_pct, a.curve[-1][0]) if a.curve else a.a_pct for a in alloys) / 100.0
    eps = np.linspace(0.0, eps_max, n)
    curves = np.vstack([ideal_curve(a, eps) for a in alloys])
    with np.errstate(all="ignore"):
        valid = ~np.all(np.isnan(curves), axis=0)
        upper = np.where(valid, np.nanmax(np.where(np.isnan(curves), -np.inf, curves), axis=0), np.nan)
        lower = np.where(valid, np.nanmin(np.where(np.isnan(curves), np.inf, curves), axis=0), np.nan)
    return eps, upper, lower, curves


# --- 5.4 Vergleichsrechnungen ----------------------------------------------------
def classify_rm(rm: float, a: Alloy) -> tuple[str, str]:
    """Einordnung nach Rm. Fehlende Spannengrenzen werden durch den Mittelwert ersetzt."""
    lo = a.rm_min if a.rm_min is not None else a.rm
    hi = a.rm_max if a.rm_max is not None else a.rm
    basis = "Spanne" if (a.rm_min is not None and a.rm_max is not None) else (
        "Mittelwert" if (a.rm_min is None and a.rm_max is None) else "Spanne unvollständig")
    if lo <= rm <= hi:
        return "schliesst ein", basis
    if rm < lo:
        return "Werkstoff darüber", basis
    return "Werkstoff darunter", basis


def compare(rm: float | None, yield_stress: float | None, fmax_n: float | None,
            alloys: list[Alloy], group: str | None = None) -> dict:
    """Rangliste der naechsten Kandidaten innerhalb der Vergleichsgruppe.
    Eine Uebereinstimmung in Rm ist keine Identifikation."""
    ratio = (rm / yield_stress) if (rm and yield_stress) else None
    rows = []
    for a in alloys:
        row = {
            "name": a.name, "category": a.category, "Rp": a.rp, "Rm": a.rm, "A": a.a_pct, "E": a.e_gpa,
            "Rm_min": a.rm_min, "Rm_max": a.rm_max, "ratio": a.ratio, "source": a.source, "basis": a.basis,
            "own": a.own,
        }
        if rm:
            row["d_rm_pct"] = 100.0 * (rm - a.rm) / rm
            row["rm_class"], row["rm_basis"] = classify_rm(rm, a)
            d_rel = abs(a.rm - rm) / rm
            d_ratio = None
            if ratio and a.ratio:
                d_ratio = abs(a.ratio - ratio) / ratio
                row["d_ratio_pct"] = 100.0 * (a.ratio - ratio) / ratio
                row["score"] = math.hypot(d_rel, d_ratio)
            else:
                row["d_ratio_pct"] = None
                row["score"] = d_rel
            if d_rel > RM_EXCLUDE_TOL:
                status = "ausgeschlossen"
            elif d_rel > RM_CANDIDATE_TOL:
                status = "unwahrscheinlich"
            elif d_ratio is not None and d_ratio > RATIO_TOL:
                status = "zurückgestuft (Verfestigungsverhältnis)"
            else:
                status = "Kandidat"
            row["status"] = status
            row["_d_rel"] = d_rel
        if fmax_n:
            area = fmax_n / a.rm
            row["A_needed_mm2"] = area
            row["d_equiv_mm"] = math.sqrt(4.0 * area / math.pi)
        rows.append(row)
    if rm:
        for i, r in enumerate(sorted(rows, key=lambda r: r["_d_rel"]), 1):
            r["rank_rm"] = i
        rows.sort(key=lambda r: r["score"])
        for i, r in enumerate(rows, 1):
            r["rank"] = i
            r.pop("_d_rel", None)
    return {"measured_ratio": ratio, "rows": rows, "group": group or DEFAULT_GROUP,
            "hinweis": "Kandidaten, keine Identifikation: eine Übereinstimmung in Rm allein bestimmt den Werkstoff nicht."}


def reference_comparison(rm: float | None, yield_stress: float | None, e_schein: float | None,
                         ref: Alloy | None) -> dict | None:
    """Gegenueberstellung Messung gegen den vom Benutzer gewaehlten Referenzwerkstoff."""
    if ref is None:
        return None
    out = {"name": ref.name, "category": ref.category, "Rp": ref.rp, "Rm": ref.rm, "A": ref.a_pct,
           "E": ref.e_gpa, "Rm_min": ref.rm_min, "Rm_max": ref.rm_max, "basis": ref.basis, "source": ref.source,
           "ratio": ref.ratio, "own": ref.own, "curve": bool(ref.curve)}
    if rm:
        out["d_rm_pct"] = 100.0 * (rm - ref.rm) / ref.rm
        out["rm_class"], out["rm_basis"] = classify_rm(rm, ref)
    if yield_stress and ref.rp:
        out["d_rp_pct"] = 100.0 * (yield_stress - ref.rp) / ref.rp
    if e_schein:
        out["e_ratio"] = e_schein / ref.e_gpa
    return out


def e_range(alloys: list[Alloy]) -> tuple[float, float]:
    es = [a.e_gpa for a in alloys]
    return min(es), max(es)
