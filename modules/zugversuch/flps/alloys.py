"""Vergleichswerkstoffe (Spezifikation Abschnitt 5).

Die Werte stehen in der gemeinsamen Werkstoffdatenbank des SDK (sdk/python/labcalc/data/materials.json, Zeilen mit
"zugversuch": true, Felder wie im früheren data/alloys.json); der Rechner liest dieselbe Datei. Mit --legierungen
kann weiterhin eine eigene Datei im alten Format (Liste oder {"werkstoffe": [...]}) angegeben werden.

Neben den Aluminiumlegierungen der Spezifikation gibt es weitere Werkstoffklassen (Stahl, Kunststoffe,
Elastomere, ...). Verglichen wird immer innerhalb einer gewaehlten Vergleichsgruppe; Voreinstellung ist Aluminium
wie in der Spezifikation.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np


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
    value_type: str = ""  # Wertart von Rm und Rp (Datenbankfeld "wertart"), z. B. "Rm Mindestwert, Rp Mindestwert"
    check_note: str = ""  # nicht leer: Wert oder Quelle nicht geprüft (Datenbankfeld "nicht_geprueft")

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
        if not isinstance(text_or_list, (list, tuple)):
            raise ValueError("Kurve: Text oder Liste von Punkten erwartet")
        for p in text_or_list:
            try:
                pts.append((float(p[0]), float(p[1])))
            except (TypeError, ValueError, IndexError, KeyError):
                raise ValueError(f"Kurve: Punkt {p!r} ist kein Zahlenpaar") from None
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
                 own=True, cite=cite, curve=curve, oid=str(d.get("id") or ""),
                 check_note="keine Quelle angegeben (importiert)" if d.get("no_source") else "")


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
    """Vergleichswerkstoffe aus der gemeinsamen Werkstoffdatenbank, oder aus ``path`` (eigene Datei im alten Format)."""
    if path:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        rows = (raw.get("werkstoffe") or raw.get("alloys") or []) if isinstance(raw, dict) else raw
    else:
        try:
            from labcalc import materials
        except ImportError:  # ausserhalb des Hubs gestartet: SDK aus dem Suite-Ordner holen (wie flps/bundle.py)
            import sys
            sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "sdk" / "python"))
            from labcalc import materials
        rows = materials.zugversuch_rows()
    out = []
    for r in rows:
        rp = r.get("Rp02_MPa")
        out.append(Alloy(
            name=r["name"], rp=float(rp) if rp is not None else None, rm=float(r["Rm_MPa"]),
            a_pct=float(r["A_pct"]), e_gpa=float(r["E_GPa"]),
            rm_min=r.get("Rm_min"), rm_max=r.get("Rm_max"), source=r.get("quelle", ""),
            category=r.get("kategorie", "Aluminium"), basis=r.get("basis", ""),
            url=r.get("url", "") or "", year=str(r.get("jahr") or ""), accessed=r.get("abgerufen", "") or "",
            value_type=_value_type(r.get("wertart")), check_note=str(r.get("nicht_geprueft") or ""),
        ))
    return out


VALUE_TYPES = {"min": "Mindestwert", "typ": "Typwert", "mitte": "Mitte der Spanne", "max": "Höchstwert",
               "unklar": "unklar"}


def _value_type(w) -> str:
    """{"Rm": "mitte", "Rp": "min"} -> "Rm Mitte der Spanne, Rp Mindestwert"."""
    if not isinstance(w, dict):
        return ""
    return ", ".join(f"{k} {VALUE_TYPES.get(v, v)}" for k, v in w.items() if v)


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
AG_FRACTION = 0.55      # Gleichmassdehnung ε_u ≈ 0,55·A (Festlegung der Spezifikation 5.2, ohne Quelle)
NECK_DROP = 0.07        # Abfall von Rm bis zum Bruch nach ε_u: 7 % (Festlegung der Spezifikation 5.2, ohne Quelle)


def curve_model(a: Alloy) -> dict:
    """Parameter der idealisierten Kurve eines Werkstoffs ohne eigene Kurve (nur zur Orientierung).

    Elastischer Anteil immer mit dem E-Modul des Werkstoffs. Mit Rp (Rp0,2 bzw. Streckspannung) bis zur
    Gleichmassdehnung ε_u = 0,55·A die Ramberg-Osgood-Beziehung (Ramberg & Osgood 1943, NACA TN 902) in der Form mit
    0,2 % Dehngrenze, ε = σ/E + 0,002·(σ/Rp)^n, mit n so gewählt, dass die Kurve bei ε_u Rm erreicht:
    n = ln((ε_u − Rm/E)/0,002) / ln(Rm/Rp). Danach linear auf 0,93·Rm bei A. Rückfälle, wenn die Kennwerte das nicht
    zulassen: "linear-E" (Rp ≥ Rm: elastisch bis Rp, dann waagrecht), "bilinear-E" (n ≤ 1 oder ε_u zu klein: elastisch bis
    Rp, dann gerade bis Rm bei ε_u), "sekante" (A kleiner als die elastische Dehnung: Gerade durch (A, Rm), die
    Kennwerte passen nicht zu linearer Elastizität). Ohne Rp: elastisch mit E bis Rm, dann waagrecht bis A ("linear-E"),
    oder "sekante", wenn Rm/E ≥ A."""
    E = a.e_gpa * 1000.0
    Rm, A = a.rm, a.a_pct / 100.0
    if not a.rp:
        return {"kind": "sekante" if Rm / E >= A else "linear-E", "E": E, "Rm": Rm, "A": A, "Rp": Rm}
    Rp = min(a.rp, Rm)
    if Rp / E >= A:
        return {"kind": "sekante", "E": E, "Rm": Rm, "A": A, "Rp": Rp}
    ey = Rp / E + 0.002
    ag = AG_FRACTION * A
    if ag <= ey:  # Gleichmassdehnung vor dem Ende der 0,2-%-Dehngrenze: Mitte zwischen ihr und A, höchstens A
        ag = min(0.5 * (ey + A), A)
    out = {"E": E, "Rm": Rm, "A": A, "Rp": Rp, "ag": ag}
    if Rm <= Rp * (1 + 1e-9):
        return {**out, "kind": "linear-E"}
    ep_u = ag - Rm / E
    n = math.log(ep_u / 0.002) / math.log(Rm / Rp) if ep_u > 0.002 else 0.0
    if n <= 1.0:
        return {**out, "kind": "bilinear-E"}
    return {**out, "kind": "ramberg-osgood", "n": n}


def ideal_curve(a: Alloy, eps: np.ndarray) -> np.ndarray:
    """sigma(eps) in MPa, eps dimensionslos. Ausserhalb 0..A ist der Wert NaN.

    Idealisierte Kurve zur Orientierung (curve_model); keine Messkurve. Hat der Werkstoff eine eigene Kurve (aus einer
    Quelle digitalisiert oder gemessen), wird sie linear interpoliert statt idealisiert.
    """
    if a.curve:
        c = np.asarray(a.curve, dtype=float)
        eps = np.asarray(eps, dtype=float)
        x = eps * 100.0
        s = np.interp(x, c[:, 0], c[:, 1])
        return np.where((x >= 0) & (x <= c[-1, 0]), s, np.nan)
    p = curve_model(a)
    E, Rm, A, Rp = p["E"], p["Rm"], p["A"], p["Rp"]
    eps = np.asarray(eps, dtype=float)
    s = np.full_like(eps, np.nan)
    inside = (eps >= 0) & (eps <= A)
    kind = p["kind"]
    if kind == "sekante":
        s[inside] = Rm * eps[inside] / A
        return s
    if not a.rp:                                     # elastisch bis Rm, dann waagrecht bis A
        s[inside] = np.minimum(E * eps[inside], Rm)
        return s
    ag = p["ag"]
    m1 = inside & (eps <= ag)
    if kind == "linear-E":
        s[m1] = np.minimum(E * eps[m1], Rp)
    elif kind == "bilinear-E":
        ey = Rp / E
        e = eps[m1]
        s[m1] = np.where(e <= ey, E * e, Rp + (Rm - Rp) * (e - ey) / (ag - ey))
    else:                                            # Ramberg-Osgood, numerisch invertiert
        n = p["n"]
        sg = np.linspace(0.0, Rm, 4001)
        with np.errstate(divide="ignore"):
            eg = sg / E + 0.002 * np.exp(n * np.log(np.where(sg > 0, sg / Rp, 1.0)))
        eg[0] = 0.0
        s[m1] = np.interp(eps[m1], eg, sg)
    m3 = (eps > ag) & (eps <= A)
    s[m3] = Rm - NECK_DROP * Rm * (eps[m3] - ag) / (A - ag)
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


STATUS_ORDER = {"Kandidat": 0, "zurückgestuft (Verfestigungsverhältnis)": 1, "unwahrscheinlich": 2, "ausgeschlossen": 3}
RANK_CRITERION = ("Rang: zuerst nach Status (Kandidat, zurückgestuft, unwahrscheinlich, ausgeschlossen), bei gleichem "
                  "Status nach |ΔRm| = |Rm − Rm_Werkstoff| / Rm_Werkstoff. Das Verfestigungsverhältnis geht nur in den "
                  "Status ein (zurückgestuft), nicht in den Abstand.")
RATIO_BASIS = ("Gemessenes Verhältnis Rm/Fliessbeginn (Abweichungsschwelle auf der Kurve) gegen Rm/Rp0,2 bzw. Rm/ReH "
               "der Quelle: nicht gleichartig, nur zur Orientierung.")


def compare(rm: float | None, yield_stress: float | None, fmax_n: float | None,
            alloys: list[Alloy], group: str | None = None) -> dict:
    """Rangliste der naechsten Kandidaten innerhalb der Vergleichsgruppe.
    Eine Uebereinstimmung in Rm ist keine Identifikation.

    Alle relativen Abweichungen beziehen sich auf den Wert des Werkstoffs: ΔRm = (Rm − Rm_W)/Rm_W,
    ΔVerh. = (Verh. − Verh._W)/Verh._W. Rangfolge siehe RANK_CRITERION."""
    ratio = (rm / yield_stress) if (rm and yield_stress) else None
    rows = []
    for a in alloys:
        row = {
            "name": a.name, "category": a.category, "Rp": a.rp, "Rm": a.rm, "A": a.a_pct, "E": a.e_gpa,
            "Rm_min": a.rm_min, "Rm_max": a.rm_max, "ratio": a.ratio, "source": a.source, "basis": a.basis,
            "own": a.own, "value_type": a.value_type, "check_note": a.check_note,
        }
        if rm:
            row["d_rm_pct"] = 100.0 * (rm - a.rm) / a.rm
            row["rm_class"], row["rm_basis"] = classify_rm(rm, a)
            d_rel = abs(rm - a.rm) / a.rm
            d_ratio = None
            if ratio and a.ratio:
                d_ratio = abs(ratio - a.ratio) / a.ratio
                row["d_ratio_pct"] = 100.0 * (ratio - a.ratio) / a.ratio
            else:
                row["d_ratio_pct"] = None
            row["score"] = d_rel                  # Abstand für die Rangfolge: nur Rm
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
        for i, r in enumerate(sorted(rows, key=lambda r: (r["_d_rel"], r["name"])), 1):
            r["rank_rm"] = i
        rows.sort(key=lambda r: (STATUS_ORDER.get(r["status"], 9), r["_d_rel"], r["name"]))
        for i, r in enumerate(rows, 1):
            r["rank"] = i
            r.pop("_d_rel", None)
    return {"measured_ratio": ratio, "rows": rows, "group": group or DEFAULT_GROUP,
            "criterion": RANK_CRITERION, "ratio_basis": RATIO_BASIS,
            "hinweis": "Kandidaten, keine Identifikation: eine Übereinstimmung in Rm allein bestimmt den Werkstoff nicht."}


def reference_comparison(rm: float | None, yield_stress: float | None, e_schein: float | None,
                         ref: Alloy | None) -> dict | None:
    """Gegenueberstellung Messung gegen den vom Benutzer gewaehlten Referenzwerkstoff."""
    if ref is None:
        return None
    out = {"name": ref.name, "category": ref.category, "Rp": ref.rp, "Rm": ref.rm, "A": ref.a_pct,
           "E": ref.e_gpa, "Rm_min": ref.rm_min, "Rm_max": ref.rm_max, "basis": ref.basis, "source": ref.source,
           "ratio": ref.ratio, "own": ref.own, "curve": bool(ref.curve), "value_type": ref.value_type,
           "check_note": ref.check_note}
    if rm:
        out["d_rm_pct"] = 100.0 * (rm - ref.rm) / ref.rm
        out["rm_class"], out["rm_basis"] = classify_rm(rm, ref)
    if yield_stress and ref.rp:
        # Fliessbeginn (Abweichungsschwelle) gegen Rp0,2/ReH der Quelle: nicht gleichartig, nur zur Orientierung
        out["d_rp_pct"] = 100.0 * (yield_stress - ref.rp) / ref.rp
        out["d_rp_basis"] = "Fliessbeginn (Schwelle) gegen Rp0,2 bzw. ReH: nicht gleichartig, nur zur Orientierung"
    if e_schein:
        out["e_ratio"] = e_schein / ref.e_gpa
    return out


def e_range(alloys: list[Alloy]) -> tuple[float, float]:
    es = [a.e_gpa for a in alloys]
    return min(es), max(es)
