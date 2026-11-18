"""A3: Geteilte TGA-Stufen mit dem theoretischen Massenverlust einer ausgeglichenen Zersetzung vergleichen.

Theoretischer Verlust einer Stufe (bezogen auf die Ausgangsprobe = 100 %):

    Verlust = Σ ν_g · M_g / (ν_E · M_Basis) · 100 %

ν_g, M_g: Koeffizienten und molare Massen der flüchtigen Produkte (Phase „(g)“), ν_E: Koeffizient des ersten Edukts,
M_Basis: molare Masse der eingewogenen Verbindung (ohne Angabe das erste Edukt selbst). Vorausgesetzt ist, dass aus
1 mol Basis 1 mol des Edukts entsteht (Zersetzungskette, z. B. CaC₂O₄·H₂O → CaC₂O₄ → CaCO₃ → CaO).
Molare Massen: Standard-Atomgewichte (CIAAW), wie überall im Modul.
"""
from __future__ import annotations

from labcalc import chem as C
from labshare import Sharebox

KIND = "tga.steps"
ME = "elementrechner"


def theoretical_loss(equation: str, basis: str = "") -> dict:
    eq = C.parse_equation(equation)
    if eq.nuclear:
        raise ValueError("Kernreaktionen haben keinen Massenverlust im Sinne der TGA")
    bal = C.balance(eq)
    if bal.get("status") not in ("ok", "given_ok"):
        raise ValueError(bal.get("message") or "Gleichung lässt sich nicht eindeutig ausgleichen")
    coefs = [float(c) for c in bal["coefs"]]
    reac = [(c, t) for c, t in zip(coefs, eq.terms) if t.side < 0]
    gases = [(c, t) for c, t in zip(coefs, eq.terms) if t.side > 0 and t.species.phase == "g"]
    if not reac:
        raise ValueError("Kein Edukt")
    if not gases:
        raise ValueError("Flüchtige Produkte bitte mit (g) kennzeichnen, z. B. CaCO3 -> CaO + CO2(g)")
    nu_r, r = reac[0]
    Mr = C.molar_mass(r.species)["M"]
    Mb = C.molar_mass(basis)["M"] if basis.strip() else Mr
    g_rows = [{"formula": t.species.unicode(), "coef": c, "M": C.molar_mass(t.species)["M"]} for c, t in gases]
    lost = sum(g["coef"] * g["M"] for g in g_rows)
    bsp = C.parse_species(basis) if basis.strip() else r.species
    return {"loss": 100.0 * lost / (nu_r * Mb), "equation": C.format_equation(eq, bal["coefs"]),
            "equation_tex": C.format_equation(eq, bal["coefs"], "latex"), "basis_tex": bsp.latex(),
            "reactant": r.species.unicode(), "M_reactant": Mr, "basis": basis.strip() or r.species.unicode(),
            "M_basis": Mb, "gases": g_rows}


def _box(envs) -> Sharebox:
    envs.ensure()
    return Sharebox(envs.suite, envs.project)


def list_shares(envs, kind: str | None = KIND) -> list[dict]:
    return _box(envs).list(ME, kind)


def board_shares(envs) -> dict:
    """UI-11: Kästen der Übersicht – was andere Module für den Elementrechner teilen (nur lesen) und was er selbst teilt."""
    box = _box(envs)
    every = box.list()
    slim = lambda m: {k: m.get(k) for k in ("id", "kind", "title", "latest", "producer", "recipients", "modified")}  # noqa: E731
    mine = lambda m: (m.get("producer") or {}).get("module") == ME  # noqa: E731
    return {"incoming": [slim(m) for m in every if ME in (m.get("recipients") or []) and not mine(m)],
            "own": [slim(m) for m in every if mine(m) and m.get("kind") != ENV_KIND],
            "envvalues": [slim(m) for m in every if mine(m) and m.get("kind") == ENV_KIND]}   # UI-15: Umgebung → Umgebung


ENV_KIND = "chem.envvalues"


def _outputs(items) -> list:
    outs = []
    for it in items or []:
        try:
            v = float(str(it.get("value", "")).replace(",", "."))
        except (TypeError, ValueError):
            continue
        outs.append({"key": str(it.get("sym", ""))[:60], "label": str(it.get("label") or it.get("sym", ""))[:200],
                     "quantity": {"value": v, "unit": str(it.get("unit") or "")[:30]}, "conditions": {"kind": it.get("kind") or ""}})
    return outs


def publish_env_values(envs, env_id: str, items: list, module_version: str = "") -> dict:
    """UI-15: Werte einer Umgebung für andere Umgebungen des Elementrechners – eine Freigabe je Quellumgebung.

    Eine neue Version entsteht nur, wenn sich ein Wert (Schlüssel, Zahl, Einheit) geändert hat; sonst bleibt die
    neueste Version gültig (`unchanged`). Live-Verbindungen folgen der neuesten Version, Momentaufnahmen behalten ihre.
    """
    envs.ensure()
    known = {e["id"]: e["name"] for e in envs.envs.list()}
    if env_id not in known:
        raise ValueError("Unbekannte Umgebung")
    outs = _outputs(items)
    if not outs:
        raise ValueError("Keine Zahlenwerte zum Teilen")
    box = _box(envs)
    prev = next((m for m in box.list(kind=ENV_KIND) if (m.get("producer") or {}).get("env") == env_id), None)
    if prev:
        last = box.get(prev["id"], prev["latest"])
        sig = lambda os: sorted((o["key"], o["quantity"]["value"], o["quantity"].get("unit", ""), o.get("label", "")) for o in os)  # noqa: E731
        if sig(last.get("outputs") or []) == sig(outs):
            return {**last, "unchanged": True}
    prod = {"module": ME, "env": env_id, "env_name": known[env_id], "item": "umgebungswerte",
            "item_name": "Werte der Umgebung", "module_version": module_version}
    return box.publish(prod, ENV_KIND, f"Werte aus „{known[env_id]}“", outs, [ME], share_id=prev["id"] if prev else None)


def get_share(envs, share_id: str, version=None) -> dict:
    return _box(envs).get(share_id, version, recipient=ME)


def publish_values(envs, items: list, module_version: str = "") -> dict:
    """A5: „An den Rechner“ als typisierte, versionierte Freigabe (kind chem.values) – je Umgebung eine Freigabe,
    jede Übergabe eine neue Version. Der Rechner hält Freigabe-ID und Version an jeder übernommenen Grösse fest."""
    outs = []
    for it in items or []:
        try:
            v = float(str(it.get("value", "")).replace(",", "."))
        except ValueError:
            continue
        outs.append({"key": str(it.get("sym", ""))[:60], "label": it.get("label") or it.get("sym", ""),
                     "quantity": {"value": v, "unit": it.get("unit", "")}, "conditions": {"kind": it.get("kind") or ""}})
    box = _box(envs)
    prev = next((m for m in box.list(kind="chem.values") if (m.get("producer") or {}).get("env") == envs.eid), None)
    env_name = next((e["name"] for e in envs.envs.list() if e["id"] == envs.eid), envs.eid)
    prod = {"module": ME, "env": envs.eid, "env_name": env_name, "item": "werte", "item_name": "Übergabe an den Rechner",
            "module_version": module_version}
    return box.publish(prod, "chem.values", "Elementrechner → Rechner", outs, ["rechner"],
                       share_id=prev["id"] if prev else None)


IR_KIND = "ftir.peaks"


def compare_ir(envelope: dict, smiles: str) -> dict:
    """A6: funktionelle Gruppen einer Struktur gegen geteilte FTIR-Banden und -Gruppenhypothesen.

    Je Gruppe: erwartete Banden (labcalc.irbands, Socrates 2001) und ob eine geteilte Bande im Bereich liegt;
    dazu das Urteil der FTIR-Gruppenauswertung für die passende Stoffklasse. Ergebnis je Gruppe:
    bestätigt (Leitbande und alle weiteren gefunden), teilweise, fehlt; „ohne IR-Bande“ für Gruppen ohne verlässliche
    Bande. Zusätzlich FTIR-Klassen, die „wahrscheinlich“ sind, aber zu keiner Gruppe der Struktur passen.
    Ein Hinweis, keine Identifizierung – Lage und Stärke von Banden hängen von Umgebung und Probe ab.
    """
    from labcalc import irbands as IR
    from labcalc import molgraph as G

    from . import design as D
    groups = D.analyze(smiles).get("groups") or []
    outs = envelope.get("outputs") or []
    peaks = [o for o in outs if o["key"].startswith("peak")]
    classes = {o["key"][6:]: o for o in outs if o["key"].startswith("class-")}
    rows, covered = [], set()
    for g in groups:
        bands, cls = IR.GROUP_BANDS.get(g["key"], ([], None))
        exp = IR.expected(g["key"])
        found = []
        for b in exp:
            hit = [p for p in peaks if b["lo"] - 5 <= p["quantity"]["value"] <= b["hi"] + 5]
            best = max(hit, key=lambda p: (p.get("conditions") or {}).get("rel", 0)) if hit else None
            found.append({"band": b["name"], "range": [b["hi"], b["lo"]], "at": best["quantity"]["value"] if best else None})
        n = sum(f["at"] is not None for f in found)
        if not exp:
            status = "ohne IR-Bande"
        elif n == len(exp):
            status = "bestätigt"
        elif found[0]["at"] is not None:
            status = "teilweise"
        else:
            status = "fehlt"
        c = classes.get(cls) if cls else None
        if cls:
            covered.add(cls)
        rows.append({"group": g["key"], "name": g["de"], "n": g.get("n", 1), "status": status, "bands": found,
                     "ftir_class": cls, "ftir_verdict": (c.get("conditions") or {}).get("verdict") if c else None})
    extra = [{"class": k, "name": o.get("label", k), "verdict": (o.get("conditions") or {}).get("verdict")}
             for k, o in classes.items()
             if k not in covered and (o.get("conditions") or {}).get("verdict") == "wahrscheinlich"
             and k not in ("alkyl", "longchain", "water")]
    p = envelope.get("producer") or {}
    return {"rows": rows, "extra": extra, "share": envelope.get("id"), "version": envelope.get("version"),
            "spectrum": p.get("item_name"), "env_name": p.get("env_name"), "groups_known": sorted(G.GROUP_NAMES)}


def resolve(envs, binding: dict) -> dict:
    """A4: Bindung (pin | copy | live) auflösen; Status current | update | stale | failed."""
    return _box(envs).resolve(binding or {}, recipient=ME)


def compare(envelope: dict, rows: list[dict]) -> list[dict]:
    """rows: [{key, equation, basis}] → gemessen (aus dem Umschlag), theoretisch, Differenz."""
    outs = {o["key"]: o for o in envelope.get("outputs", [])}
    res = []
    for r in rows or []:
        o = outs.get(r.get("key"))
        if not o or not (r.get("equation") or "").strip():
            continue
        rec = {"key": o["key"], "label": o.get("label", o["key"]), "measured": o["quantity"]["value"],
               "unit": o["quantity"].get("unit", "%")}
        try:
            th = theoretical_loss(r["equation"], r.get("basis") or "")
            rec.update(theory=th["loss"], delta=rec["measured"] - th["loss"], equation=th["equation"], basis=th["basis"],
                       equation_tex=th["equation_tex"], basis_tex=th["basis_tex"],
                       gases=th["gases"])
        except (C.ChemError, ValueError) as e:
            rec["error"] = str(e)
        res.append(rec)
    return res
