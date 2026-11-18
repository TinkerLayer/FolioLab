"""Arbeitsblatt: Groessen, Formelkarten, automatische Ableitung und Suche nach fehlenden Werten.

Alle Rechnungen intern in SI. Ein Wert ist durch (Symbol, Groessenart) eindeutig; nur wenn beides passt, wird er
automatisch in eine Formel eingesetzt (Ausnahme: genau ein Wert dieser Art vorhanden und die Formel hat nur eine
Variable dieser Art).
"""
from __future__ import annotations

import ast
import math

import numpy as np

from . import expr as E
from . import library as L
from . import render as R
from . import units as U

NO_SUBST = {"pi", "e", "MPa1", "c_std"}


class Known:
    __slots__ = ("sym", "kind", "si", "unit", "src", "label", "prov", "name")

    def __init__(self, sym, kind, si, unit, src, label="", prov=None, name=None):
        self.sym, self.kind, self.si, self.unit, self.src, self.label, self.prov = sym, kind, si, unit, src, label, prov
        self.name = name or sym          # Name des Benutzers ("Geschwindigkeit"); sym ist die Rolle in Formeln ("v")

    def to_dict(self, lang="de"):
        k = U.ensure_kind(self.kind)
        v = to_unit(self.si, self.unit, k)
        return {"sym": self.sym, "name": self.name, "kind": self.kind, "si": E._jnum(self.si), "value": E._jnum(v),
                "unit": self.unit, "text": R.qty_html(v, self.unit, lang, 5), "html": R.sym_html(self.sym),
                "name_html": R.sym_html(self.name), "src": self.src,
                "label": self.label, "prov": self.prov, "kind_de": k.de, "kind_en": k.en}


def to_si(v, unit, kind: U.Kind):
    return U.to_si(v, unit or kind.si, diff=kind.diff)


def to_unit(si, unit, kind: U.Kind):
    return U.from_si(si, unit or kind.si, diff=kind.diff)


def _num_expr(text, names=None):
    """Zahl oder kurzer Ausdruck (Konstanten, andere Groessen in SI) -> float."""
    s = str(text).strip().replace(",", ".") if isinstance(text, str) and text.count(",") == 1 and "(" not in text else str(text).strip()
    if not s:
        raise E.CalcError("leer")
    try:
        return float(s)
    except ValueError:
        pass
    v = E.evaluate(E.parse(s), E.Ctx(names=names or {}))
    v = np.asarray(v)
    if v.ndim or np.iscomplexobj(v):
        raise E.CalcError("Eine reelle Zahl erwartet")
    return float(v)


# ----------------------------------------------------------------------------- Loesen
def _ctx(vals):
    return E.Ctx(names=vals, angle="rad")


def solve_for(eq: L.Equation, target: str, vals: dict) -> list[float]:
    """Alle (reellen) Loesungen fuer target, die anderen Variablen in vals (SI)."""
    kind = U.KINDS[eq.var(target)["kind"]]
    iso = eq.isolated(target)
    if iso is not None:
        with np.errstate(all="ignore"):
            try:
                v = E.evaluate(iso, _ctx(vals))
            except (E.CalcError, ZeroDivisionError, OverflowError, ValueError):
                return []
        v = np.asarray(v)
        if v.ndim or np.iscomplexobj(v) or not np.isfinite(v):
            return []
        roots = [float(v)]
        if _has_even_power(eq, target):                    # x^2 = ... -> auch die negative Loesung
            if not kind.pos and roots[0] != 0:
                roots.append(-roots[0])
        return roots
    return numeric_roots(eq, target, vals, kind)


def _has_even_power(eq, target):
    for side in (eq.lhs, eq.rhs):
        for n in ast.walk(side):
            if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Pow) and R.count(n.left, target) and \
                    R._const_value(n.right) is not None and float(R._const_value(n.right)) % 2 == 0:
                return True
    return False


def _residual(eq, target, vals):
    lhs, rhs = eq.lhs, eq.rhs

    def f(x):
        loc = {target: x}
        with np.errstate(all="ignore"):
            a = E.evaluate(lhs, _ctx(vals), loc)
            b = E.evaluate(rhs, _ctx(vals), loc)
        a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
        return a - b, np.maximum(np.abs(a), np.abs(b))
    return f


def numeric_roots(eq, target, vals, kind: U.Kind):
    f = _residual(eq, target, vals)
    if kind.key == "angle":
        grids = [np.linspace(-math.pi, math.pi, 1441)]
    else:
        pos = np.logspace(-15, 15, 1201)
        grids = [pos] if kind.pos else [pos, -pos[::-1], np.linspace(-1, 1, 201)]
    roots = []
    for X in grids:
        try:
            Y, _ = f(X)
            Y = np.broadcast_to(Y, X.shape)
        except (E.CalcError, ValueError, TypeError):
            Y = np.array([_safe(f, x) for x in X])
        for i in range(len(X) - 1):
            a, b, ya, yb = X[i], X[i + 1], Y[i], Y[i + 1]
            if not (np.isfinite(ya) and np.isfinite(yb)):
                continue
            if ya == 0:
                roots.append(float(a))
                continue
            if ya * yb < 0:
                r = _bisect(f, float(a), float(b), float(ya))
                y, scale = f(r)
                if np.isfinite(y) and abs(float(y)) <= 1e-7 * max(1e-300, float(scale)):
                    roots.append(r)
    out = []
    for r in sorted(roots):
        if not out or abs(r - out[-1]) > 1e-9 * max(abs(r), 1e-300):
            out.append(r)
    if kind.pos:
        out = [r for r in out if r > 0]
    return out


def _safe(f, x):
    try:
        return float(f(x)[0])
    except (E.CalcError, ValueError, TypeError, ZeroDivisionError, OverflowError):
        return math.nan


def _bisect(f, a, b, fa):
    for _ in range(200):
        m = 0.5 * (a + b)
        fm = float(f(m)[0])
        if fm == 0 or abs(b - a) <= 1e-15 * max(abs(m), 1e-300):
            return m
        if (fa < 0) == (fm < 0):
            a, fa = m, fm
        else:
            b = m
    return 0.5 * (a + b)


def pick_root(roots, kind: U.Kind, index=None):
    if not roots:
        return None
    if index is not None and 0 <= index < len(roots):
        return roots[index]
    pos = [r for r in roots if r > 0]
    if kind.key == "angle":
        pos = [r for r in roots if 0 <= r <= math.pi / 2 + 1e-12] or pos
    return (pos or roots)[0]


# ----------------------------------------------------------------------------- Arbeitsblatt
class Sheet:
    def __init__(self, state: dict):
        self.state = state or {}
        self.lang = self.state.get("lang", "de")
        self.errors = {}
        self.user = {}            # (sym, kind) -> Known
        self.user_by_id = {}
        self.derived = {}         # (sym, kind) -> Known
        self.cards_out = []
        self.card_known = {}      # card id -> Known

    # ---- Groessen des Benutzers
    def load_values(self):
        names = {}
        for v in self.state.get("values", []):
            vid = str(v.get("id", ""))
            try:
                if not str(v.get("sym", "")).strip():
                    if str(v.get("value", "")).strip():
                        raise E.CalcError("Name fehlt")
                    continue
                name = E.norm_name(v.get("sym", ""))
                role = str(v.get("as") or "").strip()
                sym = E.norm_name(role) if role else name
                kind = v.get("kind") or "number"
                try:
                    k = U.ensure_kind(kind)
                except U.UnitError:
                    raise E.CalcError(f"Grössenart {kind} unbekannt") from None
                unit = v.get("unit") or k.si
                msg = U.check_unit(kind, unit)
                if msg:
                    raise E.CalcError(msg)
                raw = v.get("value", "")
                if str(raw).strip() == "":
                    continue
                si = to_si(_num_expr(raw, names), unit, k)
                if not math.isfinite(si):
                    raise E.CalcError("Wert ist nicht endlich")
                lab = v.get("label") or (k.de if self.lang == "de" else k.en)
                if kind == "ph":                          # U-01: für die Formeln ist ein pH-Wert eine Zahl
                    kind = "number"
                kn = Known(sym, kind, si, unit, "user:" + vid, lab, name=name)
                if (sym, kind) in self.user:
                    other = self.user[(sym, kind)]
                    raise E.CalcError(f"{R.plain(ast.Name(id=sym))} ({k.de}) ist schon durch „{other.name}“ belegt"
                                      + (" – andere Rolle wählen" if role else ""))
                self.user[(sym, kind)] = kn
                self.user_by_id[vid] = kn
                names[sym] = si
                names[name] = si
            except (E.CalcError, U.UnitError, ValueError) as e:
                self.errors[vid] = str(e)

    def known(self, exclude_card=None):
        out = dict(self.derived)
        for cid, kn in self.card_known.items():
            if cid != exclude_card:
                out[(kn.sym, kn.kind)] = kn
        out.update(self.user)
        return out

    # ---- Ableitung
    def derive(self, max_rounds=5, max_values=80):
        self.derived = {}
        for _ in range(max_rounds):
            added = 0
            base = self.known()
            for eq in L.EQUATIONS:
                if not eq.auto:
                    continue
                missing = [v for v in eq.vars if (v["sym"], v["kind"]) not in base]
                if len(missing) != 1:
                    continue
                t = missing[0]
                vals = {v["sym"]: base[(v["sym"], v["kind"])].si for v in eq.vars if v is not t}
                kind = U.KINDS[t["kind"]]
                roots = solve_for(eq, t["sym"], vals)
                r = pick_root(roots, kind)
                if r is None or not math.isfinite(r) or (kind.pos and r <= 0):
                    continue
                prov = {"eq": eq.id, "name": eq.de if self.lang == "de" else eq.en,
                        "from": [{"sym": v["sym"], "kind": v["kind"], "html": R.sym_html(v["sym"])} for v in eq.vars if v is not t]}
                kn = Known(t["sym"], t["kind"], r, U.auto_unit(t["kind"], r), "der", t["de"] if self.lang == "de" else t["en"], prov)
                self.derived[(t["sym"], t["kind"])] = kn
                base[(t["sym"], t["kind"])] = kn
                added += 1
                if len(self.derived) >= max_values:
                    return
            if not added:
                return

    # ---- Formelkarten
    def resolve(self, eq, var, spec, base, card_id):
        """-> (Known oder None, Herkunft)."""
        kind = U.KINDS[var["kind"]]
        raw = str(spec.get("value", "") or "").strip()
        if raw:
            unit = spec.get("unit") or kind.units[0]
            msg = U.check_unit(var["kind"], unit)
            if msg:
                raise E.CalcError(f"{R.plain(ast.Name(id=var['sym']))}: {msg}")
            names = {k[0]: kn.si for k, kn in base.items()}
            si = to_si(_num_expr(raw, names), unit, kind)
            return Known(var["sym"], var["kind"], si, unit, "manual"), "manual"
        bind = spec.get("bind") or "auto"
        if bind == "none":
            return None, "missing"
        if bind.startswith("user:"):
            kn = self.user_by_id.get(bind[5:])
            if kn is not None:
                return self._as(kn, var), bind
            return None, "missing"
        if bind.startswith("card:"):
            kn = self.card_known.get(bind[5:])
            if kn is not None and bind[5:] != card_id:
                return self._as(kn, var), bind
            return None, "missing"
        if bind.startswith("der:"):
            sym, _, kd = bind[4:].partition("|")
            kn = self.derived.get((sym, kd))
            if kn is not None:
                return self._as(kn, var), bind
            return None, "missing"
        kn = base.get((var["sym"], var["kind"]))
        if kn is not None:
            return kn, kn.src
        # Ersatz: genau ein Benutzerwert dieser Art und die Formel hat nur eine Variable dieser Art
        same_kind_vars = [v for v in eq.vars if v["kind"] == var["kind"]]
        cands = [kn for (s, kd), kn in self.user.items() if kd == var["kind"]]
        if len(same_kind_vars) == 1 and len(cands) == 1 and var["kind"] != "number":
            return self._as(cands[0], var), "kind:" + cands[0].src
        return None, "missing"

    @staticmethod
    def _as(kn, var):
        if kn.kind != var["kind"]:
            raise E.CalcError(f"{kn.sym} hat die Grössenart {U.ensure_kind(kn.kind).de}, gebraucht wird {U.KINDS[var['kind']].de}")
        return kn

    def eval_card(self, card):
        cid = str(card.get("id"))
        eq = L.BY_ID.get(card.get("eq"))
        out = {"id": cid, "eq": card.get("eq")}
        if eq is None:
            out.update(status="error", error="Formel nicht gefunden")
            return out, None
        base = self.known(exclude_card=cid)
        specs = card.get("vars") or {}
        want = card.get("target") or None
        if want and not eq.var(want):
            want = None
        resolved, src = {}, {}
        for v in eq.vars:
            kn, s = self.resolve(eq, v, specs.get(v["sym"], {}), base, cid)
            if kn is not None:
                resolved[v["sym"]] = kn
            src[v["sym"]] = s
        missing = [v["sym"] for v in eq.vars if v["sym"] not in resolved]
        if want:
            target = want
            resolved.pop(target, None)
        elif len(missing) == 1:
            target = missing[0]
        elif not missing:
            # abgeleitete Werte gelten nicht als vorgegeben: lieber diese Grösse hier ausrechnen und zeigen
            soft = [v["sym"] for v in eq.vars if src.get(v["sym"], "").startswith(("der", "card:"))]
            target = (eq.target if eq.target in soft else soft[0]) if soft else None
            if target:
                resolved.pop(target, None)
        else:
            target = eq.target if eq.target in missing else missing[0]
        miss_other = [m for m in eq.vars if m["sym"] not in resolved and m["sym"] != target]
        out["target"] = target or eq.target
        out["auto_target"] = not want
        out["vars"] = []
        for v in eq.vars:
            kn = resolved.get(v["sym"])
            d = {"sym": v["sym"], "kind": v["kind"], "html": R.sym_html(v["sym"]), "de": v["de"], "en": v["en"],
                 "src": "target" if v["sym"] == target else src.get(v["sym"]),
                 "units": U.KINDS[v["kind"]].units}
            if kn is not None and v["sym"] != target:
                d.update(si=E._jnum(kn.si), value=E._jnum(to_unit(kn.si, kn.unit, U.KINDS[v["kind"]])), unit=kn.unit,
                         text=R.qty_html(to_unit(kn.si, kn.unit, U.KINDS[v["kind"]]), kn.unit, self.lang, 5))
            out["vars"].append(d)
        sym_tex, sym_html = R.render(ast.Compare(left=eq.lhs, ops=[ast.Eq()], comparators=[eq.rhs]), lang=self.lang)
        out["eq_tex"], out["eq_html"] = sym_tex, sym_html
        if target is None:
            # alles gegeben: Probe
            vals = {s: kn.si for s, kn in resolved.items()}
            try:
                a = float(E.evaluate(eq.lhs, _ctx(vals)))
                b = float(E.evaluate(eq.rhs, _ctx(vals)))
                rel = abs(a - b) / max(abs(a), abs(b), 1e-300)
            except (E.CalcError, TypeError, ValueError):
                rel = math.nan
            out.update(status="check", check={"rel": E._jnum(rel), "ok": bool(rel < 1e-3)})
            return out, None
        if miss_other:
            out.update(status="missing", missing=[{"sym": m["sym"], "kind": m["kind"], "html": R.sym_html(m["sym"]),
                                                   "de": m["de"], "en": m["en"]} for m in miss_other])
            iso = eq.isolated(target)
            if iso is not None:
                t, h = R.render(iso, lang=self.lang)
                out["sol_tex"], out["sol_html"] = f"{R.sym_tex(target)} = {t}", f"{R.sym_html(target)} = {h}"
            return out, None
        vals = {s: kn.si for s, kn in resolved.items() if s != target}
        tv = eq.var(target)
        kind = U.KINDS[tv["kind"]]
        roots = solve_for(eq, target, vals)
        idx = card.get("root")
        r = pick_root(roots, kind, idx if isinstance(idx, int) else None)
        if r is None:
            out.update(status="error", error="Keine reelle Lösung mit diesen Werten" if self.lang == "de" else "No real solution for these values")
            return out, None
        unit = card.get("outUnit") or U.auto_unit(tv["kind"], r)
        if U.check_unit(tv["kind"], unit):
            unit = U.auto_unit(tv["kind"], r)
        val = to_unit(r, unit, kind)
        out["status"] = "ok"
        out["roots"] = [{"si": E._jnum(x), "text": R.qty_html(to_unit(x, unit, kind), unit, self.lang, 5)} for x in roots] if len(roots) > 1 else []
        out["result"] = {"sym": target, "kind": tv["kind"], "si": E._jnum(r), "value": E._jnum(val), "unit": unit,
                         "text": R.qty_html(val, unit, self.lang, 5), "tex": R.qty_tex(val, unit, self.lang, 5),
                         "units": kind.units, "label": tv["de"] if self.lang == "de" else tv["en"]}
        subs = {}
        for s, kn in resolved.items():
            if s == target:
                continue
            k = U.ensure_kind(kn.kind)
            v = to_unit(kn.si, kn.unit, k)
            u = kn.unit if kn.unit != "1" else ""
            subs[s] = (R.qty_tex(v, u, self.lang, 5), R.qty_html(v, u, self.lang, 5),
                       R.P_NEG if v < 0 else (R.P_MUL if u else R.P_ATOM))
        for c in eq.consts:
            if c in NO_SUBST:
                continue
            cv, cu = U.CONSTANTS[c][0], U.CONSTANTS[c][1]
            subs[c] = (R.qty_tex(cv, cu, self.lang, 5), R.qty_html(cv, cu, self.lang, 5), R.P_MUL)
        iso = eq.isolated(target)
        tt, th = R.sym_tex(target), R.sym_html(target)
        if iso is not None:
            a = R.render(iso, lang=self.lang)
            b = R.render(iso, subs, self.lang)
            out["sol_tex"], out["sol_html"] = f"{tt} = {a[0]}", f"{th} = {a[1]}"
            out["sub_tex"] = f"{tt} = {b[0]} = {out['result']['tex']}"
            out["sub_html"] = f"{th} = {b[1]} = <b>{out['result']['text']}</b>"
        else:
            b = R.render(ast.Compare(left=eq.lhs, ops=[ast.Eq()], comparators=[eq.rhs]), subs, self.lang)
            out["sol_tex"], out["sol_html"] = sym_tex, sym_html
            out["sub_tex"] = f"{b[0]} \\;\\Rightarrow\\; {tt} = {out['result']['tex']}"
            out["sub_html"] = f"{b[1]} ⇒ {th} = <b>{out['result']['text']}</b>"
            out["numeric"] = True
        kn = Known(target, tv["kind"], r, unit, "card:" + cid, tv["de"] if self.lang == "de" else tv["en"],
                   {"eq": eq.id, "name": eq.de if self.lang == "de" else eq.en})
        return out, kn

    def run(self):
        self.load_values()
        if self.state.get("derive", True):
            self.derive()
        cards = self.state.get("cards", [])
        outs = {}
        for _ in range(max(2, len(cards) + 1)):
            changed = False
            for c in cards:
                try:
                    o, kn = self.eval_card(c)
                except (E.CalcError, U.UnitError, ValueError) as e:
                    o, kn = {"id": str(c.get("id")), "eq": c.get("eq"), "status": "error", "error": str(e)}, None
                cid = str(c.get("id"))
                prev = self.card_known.get(cid)
                if kn is None:
                    if prev is not None:
                        del self.card_known[cid]
                        changed = True
                elif prev is None or abs(prev.si - kn.si) > 1e-12 * max(1, abs(kn.si)) or prev.sym != kn.sym:
                    self.card_known[cid] = kn
                    changed = True
                outs[cid] = o
            if self.state.get("derive", True) and changed:
                self.derive()
            if not changed:
                break
        self.cards_out = [outs[str(c.get("id"))] for c in cards]
        self._mark_cycles()
        return self

    # ---- A4: Abhängigkeiten zwischen Karten, Zirkelbezüge
    def _cards_behind(self, src: str, sym: str, kind: str, seen=None) -> set:
        """Karten, aus denen ein eingesetzter Wert stammt (direkt oder über abgeleitete Werte)."""
        src = src or ""
        if src.startswith("kind:"):
            src = src[5:]
        if src.startswith("card:"):
            return {src[5:]}
        if src.startswith("der"):
            seen = seen or set()
            kn = self.derived.get((sym, kind))
            if kn is None or (sym, kind) in seen:
                return set()
            seen.add((sym, kind))
            out = set()
            for f in (kn.prov or {}).get("from", []):
                k2 = self.known().get((f["sym"], f["kind"]))
                if k2 is not None:
                    out |= self._cards_behind(k2.src, f["sym"], f["kind"], seen)
            return out
        return set()

    def card_graph(self) -> dict:
        g = {}
        for o in self.cards_out:
            deps = set()
            for v in o.get("vars") or []:
                if v.get("src") not in (None, "target", "missing"):
                    deps |= self._cards_behind(v["src"], v["sym"], v["kind"])
            g[o["id"]] = deps
        return g

    def _mark_cycles(self):
        import labdeps
        g = self.card_graph()
        bad = labdeps.in_cycles(g)
        for o in self.cards_out:
            if o["id"] in bad:
                others = sorted(d for d in g[o["id"]] if d in bad)
                o["cycle"] = others or [o["id"]]
                o.setdefault("notes", []).append("Zirkelbezug: diese Karte hängt über andere Karten von ihrem eigenen "
                                                 "Ergebnis ab – das Ergebnis ist nicht eindeutig. Einen Wert fest vorgeben.")

    def to_dict(self):
        return {"errors": self.errors,
                "values": [kn.to_dict(self.lang) | {"id": vid} for vid, kn in self.user_by_id.items()],
                "derived": [kn.to_dict(self.lang) for kn in self.derived.values()],
                "card_values": [kn.to_dict(self.lang) | {"card": cid} for cid, kn in self.card_known.items()],
                "cards": self.cards_out}


def eval_sheet(state):
    return Sheet(state).run().to_dict()


# ----------------------------------------------------------------------------- Gesuchte Groesse
def goal(state, sym=None, kind=None, limit=30):
    """Welche Formeln liefern die gesuchte Groesse, und welche Werte fehlen dafuer?"""
    sh = Sheet(state)
    sh.load_values()
    if state.get("derive", True):
        sh.derive()
    for c in state.get("cards", []):
        try:
            _, kn = sh.eval_card(c)
            if kn is not None:
                sh.card_known[str(c.get("id"))] = kn
        except (E.CalcError, U.UnitError, ValueError):
            pass
    base = sh.known()
    sym = E.norm_name(sym) if sym else None
    lib_syms = {v["sym"] for e in L.EQUATIONS for v in e.vars}
    if sym and sym not in lib_syms:                    # eigener Name ("Geschwindigkeit") -> Rolle in den Formeln
        hit = next((kn for kn in sh.user.values() if kn.name == sym), None)
        if hit is not None:
            sym, kind = hit.sym, kind or hit.kind
        else:
            from . import recognize as RC
            best = RC.recognize(sym, "", kind, sh.lang)["best"]
            if best and best["score"] >= 0.7 and not best.get("own"):
                sym, kind = best["sym"], kind or best["kind"]
    if not kind and sym:
        kinds = {v["kind"] for e in L.EQUATIONS for v in e.vars if v["sym"] == sym}
        kind = next(iter(kinds)) if len(kinds) == 1 else None
    have = {(k[0], k[1]) for k in base}
    user_kinds = {}
    for (s, kd), kn in sh.user.items():
        user_kinds.setdefault(kd, []).append(s)

    def missing_of(eq, t):
        return [v for v in eq.vars if v is not t and (v["sym"], v["kind"]) not in have]

    def producers(v, skip):
        res = []
        for e in L.EQUATIONS:
            if e is skip:
                continue
            t = next((x for x in e.vars if x["sym"] == v["sym"] and x["kind"] == v["kind"]), None)
            if t is None:
                continue
            m = missing_of(e, t)
            if len(m) <= 1:
                res.append({"eq": e.id, "name": e.de if sh.lang == "de" else e.en,
                            "missing": [_vd(x, sh.lang) for x in m]})
        res.sort(key=lambda r: len(r["missing"]))
        return res[:4]

    rows = []
    for eq in L.EQUATIONS:
        for t in eq.vars:
            if kind and t["kind"] != kind:
                continue
            if not kind and t["sym"] != sym:
                continue
            exact = sym is None or t["sym"] == sym
            m = missing_of(eq, t)
            miss = []
            for v in m:
                d = _vd(v, sh.lang)
                if v["kind"] in user_kinds:
                    d["hint"] = [s for s in user_kinds[v["kind"]]]
                if len(m) <= 3:
                    d["via"] = producers(v, eq)
                miss.append(d)
            rows.append({"eq": eq.id, "name": eq.de if sh.lang == "de" else eq.en, "cat": eq.cat, "sub": eq.sub,
                         "target": t["sym"], "target_html": R.sym_html(t["sym"]), "exact": exact, "auto": eq.auto,
                         "missing": miss, "html": eq.to_dict()["html"]})
    rows.sort(key=lambda r: (not r["exact"], len(r["missing"]), not r["auto"]))
    known_now = base.get((sym, kind)) if sym and kind else None
    return {"sym": sym, "kind": kind, "rows": rows[:limit], "total": len(rows),
            "known": known_now.to_dict(sh.lang) if known_now else None}


def _vd(v, lang):
    k = U.KINDS[v["kind"]]
    return {"sym": v["sym"], "kind": v["kind"], "html": R.sym_html(v["sym"]), "label": v["de"] if lang == "de" else v["en"],
            "kind_label": k.de if lang == "de" else k.en, "units": k.units}


# ----------------------------------------------------------------------------- Kurve aus einer Formelkarte
def card_curve(state, card_id, xvar, x0, x1, n=200, log=False):
    sh = Sheet(state).run()
    card = next((c for c in state.get("cards", []) if str(c.get("id")) == str(card_id)), None)
    out = next((o for o in sh.cards_out if o.get("id") == str(card_id)), None)
    if card is None or out is None or out.get("status") != "ok":
        raise E.CalcError("Die Formelkarte hat noch kein Ergebnis")
    eq = L.BY_ID[card["eq"]]
    target = out["result"]["sym"]
    if xvar == target or not eq.var(xvar):
        raise E.CalcError("x-Variable muss eine der gegebenen Grössen sein")
    vals = {v["sym"]: v["si"] for v in out["vars"] if v.get("si") is not None and v["sym"] != target}
    xv = eq.var(xvar)
    xk, tk = U.KINDS[xv["kind"]], U.KINDS[eq.var(target)["kind"]]
    xunit = next((v["unit"] for v in out["vars"] if v["sym"] == xvar), None) or xk.units[0]
    yunit = out["result"]["unit"]
    X = np.geomspace(x0, x1, n) if log and x0 > 0 and x1 > 0 else np.linspace(x0, x1, n)
    Y = []
    prev = None
    for x in X:
        vv = dict(vals)
        vv[xvar] = to_si(float(x), xunit, xk)
        roots = solve_for(eq, target, vv)
        if not roots:
            Y.append(math.nan)
            continue
        if prev is not None and len(roots) > 1:
            r = min(roots, key=lambda q: abs(q - prev))
        else:
            r = pick_root(roots, tk, card.get("root") if isinstance(card.get("root"), int) else None)
        prev = r
        Y.append(to_unit(r, yunit, tk))
    return {"x": [float(x) for x in X], "y": [E._jnum(y) for y in Y], "xunit": xunit, "yunit": yunit,
            "xsym": xvar, "ysym": target, "xhtml": R.sym_html(xvar), "yhtml": R.sym_html(target),
            "name": eq.de if (state or {}).get("lang", "de") == "de" else eq.en}
