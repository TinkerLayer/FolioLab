"""Grafikrechner mit Ausdrucksliste: jede Zeile ist ein Ausdruck, die Art ergibt sich aus der Schreibweise.

  y = x^2 - 2          Funktion von x            x = sin(y)       Funktion von y
  f(x) = a x^2 + b     benannte Funktion          r = 1 + cos(θ)   Polarkurve
  (cos(t), sin(t))     Parameterkurve             (2, 3)           Punkt
  x^2 + y^2 = 4        implizite Kurve            a = 1.5          Schieberegler
  b = 2a               Konstante                  integral(…)      Wert (wird angezeigt)
  y1 ~ m x1 + b        Regression über Tabellenspalten; m und b stehen danach den anderen Zeilen zur Verfügung

Wie bei Grafikrechnern üblich gilt ``ax`` als a·x, wenn es keinen Namen ``ax`` gibt, und ``sinx`` als sin(x).
Die Reihenfolge der Zeilen spielt keine Rolle. Tabellen sind Zeilen mit ``kind: "table"``.

G-01: Zeilen mit ``kind: "dataset"`` verweisen auf einen Datensatz der Datenaufbereitung ({id, mode, version, x, y});
der Server liest die Werte selbst (``DATASETS``, vom Server gesetzt) und schickt nur so viele Punkte, wie der
Ausschnitt zeigen kann (Punkte: eine je Bildschirmzelle; Linie: Minimum und Maximum je Abschnitt). Die Spalten
stehen den anderen Zeilen mit allen Werten zur Verfügung (Name = Spaltenschlüssel, ab dem zweiten Datensatz _2 …).
G-02: Zeilen mit ``kind: "fit"`` passen ein Modell an eine Tabelle oder einen Datensatz an ({of, y, model, mode,
range}); siehe labcalc.fitting.
"""
from __future__ import annotations

import ast
import math
import re

import numpy as np

from labcalc import fitting as F

from . import expr as E
from . import plots as P
from . import render as R
from . import units as U
from .console import RESERVED

DATASETS = None              # (spec) -> {title, version, latest, status, rows, producer, columns, cols{key: array}}
MAX_PTS = 4000               # bis dahin gehen alle Punkte an die Seite
MAX_CELLS = 30000

LOCALS = {"x", "y", "t", "theta", "r"}
_BINDING = {"integral", "deriv", "nsolve", "sum", "prod"}
_ATOMS = set(E.GREEK.values()) | {"lambda_", "pi"}
_SPLIT_FUNCS = [f for f in ("asin", "acos", "atan", "sinh", "cosh", "tanh", "sqrt", "sin", "cos", "tan", "exp", "abs",
                            "ln", "log") if f in E.BUILTINS]
NUM = re.compile(r"^\s*[-+]?\s*(\d+([.,]\d*)?|[.,]\d+)([eE][-+]?\d+)?\s*$")
NAME = re.compile(r"^\s*([^\W\d]\w*)\s*$")
FUNC = re.compile(r"^\s*([^\W\d]\w*)\s*\(([^()]*)\)\s*$")
_EVAL_ERR = (E.CalcError, U.UnitError, ValueError, TypeError, ZeroDivisionError, OverflowError, IndexError,
             np.linalg.LinAlgError)


# ----------------------------------------------------------------------------- Zerlegen
def _top_positions(s: str, ch: str):
    depth = 0
    for i, c in enumerate(s):
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == ch and depth == 0:
            yield i


def _eq_index(s: str) -> int:
    for i in _top_positions(s, "="):
        prev = s[i - 1] if i else ""
        nxt = s[i + 1] if i + 1 < len(s) else ""
        if prev not in "<>!=" and nxt != "=":
            return i
    return -1


def _pair(s: str):
    s = s.strip()
    if not (s.startswith("(") and s.endswith(")")):
        return None
    depth = 0
    for i, c in enumerate(s):
        depth += c in "([{"
        depth -= c in ")]}"
        if depth == 0 and i < len(s) - 1:
            return None                        # die erste Klammer schliesst vor dem Ende
    inner = s[1:-1]
    cut = list(_top_positions(inner, ","))
    if len(cut) != 1:
        return None
    return inner[:cut[0]].strip(), inner[cut[0] + 1:].strip()


def classify(src: str):
    s = str(src or "").strip()
    if not s:
        return ("empty",)
    for g, n in E.GREEK.items():
        s = s.replace(g, f" {n} ")
    s = re.sub(r"\s+", " ", s).strip()
    tl = next(_top_positions(s, "~"), -1)
    if tl >= 0:
        return ("reg", s[:tl].strip(), s[tl + 1:].strip())
    i = _eq_index(s)
    if i >= 0:
        lhs, rhs = s[:i].strip(), s[i + 1:].strip()
        if not rhs or not lhs:
            raise E.CalcError("Auf beiden Seiten des = muss etwas stehen")
        m = NAME.match(lhs)
        if m:
            n = E.norm_name(m.group(1))
            if n in ("y", "x", "r"):
                return (n, rhs)
            return ("def", n, rhs)
        m = FUNC.match(lhs)
        if m:
            args = [a.strip() for a in m.group(2).split(",") if a.strip()]
            if args and all(re.fullmatch(r"[^\W\d]\w*", a) for a in args):
                return ("func", E.norm_name(m.group(1)), [E.norm_name(a) for a in args], rhs)
        return ("eq", lhs, rhs)
    p = _pair(s)
    if p:
        return ("pair", p[0], p[1])
    return ("expr", s)


# ----------------------------------------------------------------------------- Namen
class _Fix(ast.NodeTransformer):
    """Unbekannte Namen wie ``ax`` in a·x zerlegen, ``sinx`` in sin(x); freie Namen sammeln."""

    def __init__(self, known):
        self.known = known
        self.free = set()
        self.used = set()

    def visit_Call(self, node):
        fn = node.func.id if isinstance(node.func, ast.Name) else ""
        bound = None
        if fn in _BINDING and len(node.args) >= 2 and isinstance(node.args[1], ast.Name):
            bound = node.args[1].id                      # integral(f(x), x, 0, 1): x ist hier gebunden
        if bound is None:
            node.args = [self.visit(a) for a in node.args]
            return node
        before, had = set(self.used), bound in self.known
        self.known = self.known | {bound}
        node.args = [self.visit(a) for a in node.args]
        if not had:
            self.known = self.known - {bound}
        self.used = before | (self.used - {bound})
        return node

    def visit_Name(self, node):
        n = node.id
        if n in self.known or n in U.CONSTANTS or n in ("inf", "nan", "i", "j"):
            self.used.add(n)
            return node
        rep = self._split(n)
        if rep is None:
            self.free.add(n)
            self.used.add(n)
            return node
        return rep

    def _resolvable(self, s):
        return self._pieces(s) is not None

    def _pieces(self, s):
        if not re.fullmatch(r"[A-Za-z]+", s) or len(s) < 2:
            return None
        atoms = self.known | _ATOMS
        out, i = [], 0
        while i < len(s):
            for j in range(len(s), i + 1, -1):
                if s[i:j] in atoms:
                    out.append(s[i:j])
                    i = j
                    break
            else:
                out.append(s[i])
                i += 1
        return out

    def _split(self, n):
        for f in _SPLIT_FUNCS:
            if n.startswith(f) and len(n) > len(f):
                rest = n[len(f):]
                arg = self.visit_Name(ast.Name(id=rest, ctx=ast.Load()))
                return ast.Call(func=ast.Name(id=f, ctx=ast.Load()), args=[arg], keywords=[])
        pieces = self._pieces(n)
        if not pieces:
            return None
        node = None
        for p in pieces:
            (self.used if p in self.known or p in U.CONSTANTS else self.free).add(p)
            self.used.add(p)
            nm = ast.Name(id=p, ctx=ast.Load())
            node = nm if node is None else ast.BinOp(left=node, op=ast.Mult(), right=nm)
        return node


def _parse(src, callables, known):
    node = E.parse(src, callables)
    fx = _Fix(known)
    node = fx.visit(node)
    return node, fx.free, fx.used


def _html(*parts):
    try:
        return " ".join(parts)
    except TypeError:
        return None


def _r(node, lang):
    try:
        return R.render(node, lang=lang)[1]
    except Exception:  # noqa: BLE001 - Darstellung ist nur Beiwerk
        return None


# ----------------------------------------------------------------------------- Auswerten
def _vec(node, ctx, var, X):
    return P.eval_vec(lambda v: E.evaluate(node, ctx, {var: v}), X)


def _grid_eval(node, ctx, X, Y):
    with np.errstate(all="ignore"):
        try:
            Z = np.asarray(E.evaluate(node, ctx, {"x": X, "y": Y}))
            if np.iscomplexobj(Z):
                Z = np.where(np.abs(Z.imag) < 1e-12 * np.maximum(1, np.abs(Z.real)), Z.real, np.nan)
            Z = np.asarray(Z, dtype=float)
            if Z.shape == X.shape:
                return Z
            if Z.ndim == 0:
                return np.full(X.shape, float(Z))
        except _EVAL_ERR:
            pass
    out = np.empty(X.shape)
    for k in range(X.size):
        try:
            z = complex(np.asarray(E.evaluate(node, ctx, {"x": float(X[k]), "y": float(Y[k])})))
            out[k] = z.real if abs(z.imag) < 1e-12 * max(1, abs(z.real)) else np.nan
        except _EVAL_ERR:
            out[k] = np.nan
    return out


def contour(node, ctx, view, nx=180, ny=130):
    """Nullstellenlinie von F(x, y) mit Marching Squares; Liste flacher Segmente [x0, y0, x1, y1]."""
    x0, x1 = float(view.get("xmin", -10)), float(view.get("xmax", 10))
    y0, y1 = float(view.get("ymin", -10)), float(view.get("ymax", 10))
    xs, ys = np.linspace(x0, x1, nx), np.linspace(y0, y1, ny)
    GX, GY = np.meshgrid(xs, ys)
    F = _grid_eval(node, ctx, GX.ravel(), GY.ravel()).reshape(GY.shape)
    pos = F > 0
    fin = np.isfinite(F)
    cell = (pos[:-1, :-1] != pos[:-1, 1:]) | (pos[:-1, :-1] != pos[1:, :-1]) | (pos[:-1, :-1] != pos[1:, 1:])
    cell &= fin[:-1, :-1] & fin[:-1, 1:] & fin[1:, :-1] & fin[1:, 1:]
    scale = np.nanmedian(np.abs(F[fin])) if fin.any() else 1.0
    segs = []
    for j, i in zip(*np.nonzero(cell)):
        c = [(xs[i], ys[j]), (xs[i + 1], ys[j]), (xs[i + 1], ys[j + 1]), (xs[i], ys[j + 1])]
        v = [F[j, i], F[j, i + 1], F[j + 1, i + 1], F[j + 1, i]]
        if scale > 0 and min(abs(a) for a in v) > 50 * scale:
            continue                              # Polstelle, kein Nulldurchgang
        pts = []
        for a, b in ((0, 1), (1, 2), (2, 3), (3, 0)):
            if (v[a] > 0) != (v[b] > 0):
                t = v[a] / (v[a] - v[b])
                pts.append((c[a][0] + t * (c[b][0] - c[a][0]), c[a][1] + t * (c[b][1] - c[a][1])))
        if len(pts) == 2:
            segs.append([*pts[0], *pts[1]])
        elif len(pts) == 4:
            segs.append([*pts[0], *pts[1]])
            segs.append([*pts[2], *pts[3]])
    return [[float(v) for v in s] for s in segs]


def _cell(v, ctx):
    s = str(v if v is not None else "").strip()
    if not s:
        return np.nan
    try:
        return float(s.replace(",", "."))
    except ValueError:
        pass
    try:
        z = E.evaluate(E.parse(s, ctx.callables()), ctx)
        return float(np.real(z))
    except _EVAL_ERR:
        return np.nan


def regress(lhs, rhs, params, ctx):
    """Kleinste Quadrate (Levenberg-Marquardt, numerische Ableitungen) für beliebige Modelle lhs ~ rhs."""
    with np.errstate(all="ignore"):
        Yv = np.asarray(E.evaluate(lhs, ctx), dtype=float).ravel()

        def model(p):
            m = np.asarray(E.evaluate(rhs, ctx, dict(zip(params, p))), dtype=float)
            return np.broadcast_to(m, Yv.shape).astype(float) if m.shape != Yv.shape else m

        base = model(np.ones(len(params)))
        mask = np.isfinite(Yv) & np.isfinite(base)
        if mask.sum() < max(2, len(params)):
            raise E.CalcError(f"Zu wenige Wertepaare für {len(params)} Parameter")

        def sse(p):
            r = model(p)[mask] - Yv[mask]
            return float(np.sum(r * r)) if np.all(np.isfinite(r)) else math.inf

        best_p, best_s = None, math.inf
        n = len(params)
        starts = [np.ones(n), np.full(n, 0.5), np.full(n, -1.0), np.full(n, 0.1), np.full(n, 2.0)] if n else [np.zeros(0)]
        for p in starts:
            p = p.astype(float)
            s = sse(p)
            lam = 1e-3
            for _ in range(200 if n else 0):
                r = model(p)[mask] - Yv[mask]
                J = np.empty((mask.sum(), n))
                for k in range(n):
                    h = 1e-7 * max(1.0, abs(p[k]))
                    q = p.copy()
                    q[k] += h
                    J[:, k] = (model(q)[mask] - model(p)[mask]) / h
                if not np.all(np.isfinite(J)):
                    break
                A = J.T @ J
                g = J.T @ r
                improved = False
                for _ in range(12):
                    try:
                        dp = np.linalg.solve(A + lam * np.diag(np.diag(A) + 1e-12), -g)
                    except np.linalg.LinAlgError:
                        lam *= 10
                        continue
                    s2 = sse(p + dp)
                    if s2 < s:
                        p, improved = p + dp, True
                        conv = s - s2 <= 1e-14 * max(1.0, s)
                        s = s2
                        lam = max(lam / 10, 1e-12)
                        break
                    lam *= 10
                if not improved or conv:
                    break
            if s < best_s:
                best_p, best_s = p, s
        if best_p is None or not math.isfinite(best_s):
            raise E.CalcError("Anpassung konvergiert nicht – Startwerte über Schieberegler oder anderes Modell versuchen")
        y = Yv[mask]
        sst = float(np.sum((y - y.mean()) ** 2))
        r2 = 1 - best_s / sst if sst > 0 else 1.0
        # Unsicherheiten wie im Anpassen-Werkzeug: Kovarianz (SSE/(n − p))·(JᵀJ)⁺ am Optimum (Jacobi-Matrix mit
        # Vorwärtsdifferenzen), 95 % mit dem Student-t-Quantil; Konvergenz nach dem Gradientenkriterium.
        m = int(mask.sum())
        dof = m - n
        J = np.empty((m, n))
        f0 = model(best_p)[mask]
        for k in range(n):
            h = 1e-7 * max(1.0, abs(best_p[k]))
            q = best_p.copy()
            q[k] += h
            J[:, k] = (model(q)[mask] - f0) / h
        conv = F.converged(J, f0 - y, y) if n else True
        u = [None] * n
        if dof > 0 and n and np.all(np.isfinite(J)):
            cov = (best_s / dof) * np.linalg.pinv(J.T @ J)
            u = [float(math.sqrt(cov[k, k])) if cov[k, k] >= 0 else None for k in range(n)]
        t = F.stats.t_ppf(0.975, dof) if dof > 0 else None
        info = {"u": dict(zip(params, u)), "t": t, "dof": dof, "converged": bool(conv),
                "ci": {p: (t * v if (t is not None and v is not None) else None) for p, v in zip(params, u)}}
        return dict(zip(params, (float(v) for v in best_p))), r2, m, info


def _first_local(used, *cands):
    return next((c for c in cands if c in used), None)


# ----------------------------------------------------------------------------- G-01: grosse Datensätze
def _ds_name(key: str, k: int) -> str:
    try:
        n = E.norm_name(str(key))
    except E.CalcError:
        n = re.sub(r"\W+", "_", str(key)).strip("_") or "spalte"
        if not re.match(r"[^\W\d]", n):
            n = "c_" + n
    return n if k == 0 else f"{n}_{k + 1}"


def _runs(pos):
    """Aufeinanderfolgende Positionen in Abschnitte teilen."""
    if pos.size == 0:
        return []
    return np.split(pos, np.nonzero(np.diff(pos) > 1)[0] + 1)


def thin(x, y, style, view):
    """Punkte für die Anzeige auswählen. view = (x0, x1, y0, y1, w, h).

    Gibt (Indizes mit -1 als Linienunterbrechung, Stil, Zahl endlicher Punkte). Punkte: alle im Ausschnitt, bei mehr
    als MAX_PTS einer je Bildschirmzelle (2 px, gröber, bis höchstens MAX_CELLS übrig bleiben). Linie: Punkte im
    x-Bereich samt Nachbarn; bei mehr als MAX_PTS je Abschnitt von k Punkten Minimum und Maximum in Reihenfolge."""
    x0, x1, y0, y1, w, h = view
    fin = np.isfinite(x) & np.isfinite(y)
    idx = np.nonzero(fin)[0]
    n = int(idx.size)
    if style not in ("pts", "line"):
        dx = np.diff(x[idx])
        style = "line" if n > 2000 and dx.size and float((dx >= 0).mean()) >= 0.98 else "pts"
    if n <= MAX_PTS:
        return idx, style, n
    xs, ys = x[idx], y[idx]
    mx, my = abs(x1 - x0) * 0.05, abs(y1 - y0) * 0.05
    if style == "line":
        inx = (xs >= x0 - mx) & (xs <= x1 + mx)
        keep = inx.copy()
        keep[1:] |= inx[:-1]
        keep[:-1] |= inx[1:]
        pos = np.nonzero(keep)[0]
        if pos.size <= MAX_PTS:
            out = []
            for run in _runs(pos):
                out.extend(idx[run].tolist())
                out.append(-1)
            return np.array(out[:-1] if out else [], dtype=np.int64), style, n
        k = max(1, math.ceil(pos.size / (2 * max(w, 100))))
        out = []
        for run in _runs(pos):
            for i in range(0, run.size, k):
                c = run[i:i + k]
                a, b = int(c[np.argmin(ys[c])]), int(c[np.argmax(ys[c])])
                out.extend([idx[min(a, b)], idx[max(a, b)]] if a != b else [idx[a]])
            out.append(-1)
        return np.array(out[:-1], dtype=np.int64), style, n
    inv = (xs >= x0 - mx) & (xs <= x1 + mx) & (ys >= y0 - my) & (ys <= y1 + my)
    sel = idx[inv]
    if sel.size <= MAX_PTS:
        return sel, style, n
    cell, sx, sy = 2.0, max(abs(x1 - x0), 1e-300), max(abs(y1 - y0), 1e-300)
    while True:
        cx = np.floor((x[sel] - x0) / sx * w / cell).astype(np.int64)
        cy = np.floor((y[sel] - y0) / sy * h / cell).astype(np.int64)
        _, first = np.unique(cx * 1_000_003 + cy, return_index=True)
        if first.size <= MAX_CELLS or cell >= 32:
            break
        cell *= 2
    return sel[np.sort(first)], style, n


def _take(a, ix):
    """Werte an den Indizes; -1 wird zur Lücke (None)."""
    return [None if i < 0 else E._jnum(a[i]) for i in ix.tolist()]


def _dataset_rows(rows, out, cols, ctx, data_of, view, resolve):
    """Datensatz-Zeilen auflösen: Spalten in den Kontext, ausgedünnte Reihen für die Anzeige."""
    k = -1
    for r in rows:
        if r.get("kind") != "dataset":
            continue
        k += 1
        rid = str(r["id"])
        spec = r.get("ds") or {}
        try:
            if resolve is None:
                raise E.CalcError("Datensätze sind hier nicht lesbar (keine Projektumgebung)")
            d = resolve(spec)
        except Exception as e:  # noqa: BLE001 - jeder Lesefehler landet als Meldung an der Zeile
            out[rid] = {"type": "error", "error": str(e)}
            continue
        meta = {c["key"]: c for c in d.get("columns") or []}
        xkey = spec.get("x")
        ykeys = [y for y in spec.get("y") or [] if y != xkey]
        keys = [kk for kk in [xkey, *ykeys] if kk]
        missing = [kk for kk in keys if kk not in d["cols"]]
        if missing:
            out[rid] = {"type": "error", "error": "Spalte fehlt in dieser Version: " + ", ".join(missing)}
            continue
        names = {kk: _ds_name(kk, k) for kk in keys}
        dup = [names[kk] for kk in keys if names[kk] in cols]
        if dup:
            out[rid] = {"type": "error", "error": f"Spalte {dup[0]} gibt es schon"}
            continue
        for kk in keys:
            cols[names[kk]] = d["cols"][kk]
            ctx.names[names[kk]] = d["cols"][kk]
            ctx.dims.pop(names[kk], None)
        ext = {}
        for kk in keys:
            a = d["cols"][kk]
            f = a[np.isfinite(a)]
            ext[kk] = [E._jnum(f.min()), E._jnum(f.max())] if f.size else None
        info = {"title": d.get("title"), "version": d.get("version"), "latest": d.get("latest"), "status": d.get("status"),
                "rows": d.get("rows"), "producer": d.get("producer"), "names": names, "ext": ext,
                "units": {kk: (meta.get(kk) or {}).get("unit") or "" for kk in keys},
                "labels": {kk: (meta.get(kk) or {}).get("name") or kk for kk in keys}}
        series = []
        if xkey:
            X = d["cols"][xkey]
            for j, yk in enumerate(ykeys, 1):
                Y = d["cols"][yk]
                ix, style, n = thin(X, Y, r.get("style") or "auto", view)
                series.append({"col": j, "name": names[yk], "key": yk, "x": _take(X, ix), "y": _take(Y, ix),
                               "line": style == "line", "n": n, "sent": int((ix >= 0).sum())})
            data_of[rid] = {"x": (names[xkey], X, info["units"][xkey], xkey),
                            "ys": [(names[yk], d["cols"][yk], info["units"][yk], yk) for yk in ykeys],
                            "title": d.get("title") or ""}
        out[rid] = {"type": "table", "columns": [names[kk] for kk in keys], "series": series, "ds": info}


def _fit_rows(rows, out, data_of, view, nfx, yspan, lang):
    """G-02: Anpassungen an Tabellen- oder Datensatz-Zeilen."""
    x0, x1 = view[0], view[1]
    for r in rows:
        if r.get("kind") != "fit":
            continue
        rid = str(r["id"])
        src = data_of.get(str(r.get("of") or ""))
        if not src or not src["ys"]:
            out[rid] = {"type": "error", "error": "Die Zeile mit den Messwerten fehlt oder hat keine y-Spalte"}
            continue
        want = r.get("y")
        ysel = next((t for t in src["ys"] if want in (t[0], t[3])), src["ys"][0])
        xname, X, xunit, _xk = src["x"]
        yname, Y, yunit, ykey = ysel
        mask = np.isfinite(X) & np.isfinite(Y)
        rng = r.get("range")
        if isinstance(rng, (list, tuple)) and len(rng) == 2:
            try:
                lo, hi = sorted(float(v) for v in rng)
                mask &= (X >= lo) & (X <= hi)
                rng = [lo, hi]
            except (TypeError, ValueError):
                rng = None
        else:
            rng = None
        try:
            res = F.fit(X[mask], Y[mask], str(r.get("model") or "lin"), str(r.get("mode") or "lin"), xunit, yunit, lang)
        except (F.FitError, np.linalg.LinAlgError, ValueError) as e:
            out[rid] = {"type": "error", "error": str(e)}
            continue
        Xs = np.linspace(x0, x1, nfx)
        Ys = F.predict(res["model"], [p["value"] if p["value"] is not None else math.nan for p in res["params"]], Xs, xunit)
        xs_, ys_ = P._breaks(Xs, np.asarray(Ys, dtype=float), yspan)
        out[rid] = {**res, "type": "fit", "x": xs_, "y": ys_, "xname": xname, "yname": yname, "ykey": ykey,
                    "ynames": [t[0] for t in src["ys"]], "ykeys": [t[3] for t in src["ys"]], "range": rng,
                    "of_title": src.get("title") or ""}


def compute(req: dict, resolve=None) -> dict:
    """Alle Zeilen auswerten. Antwort: {"rows": {id: {...}}}, dazu "poi" für die Zeile ``focus``.

    ``resolve(spec)`` liest einen Datensatz (G-01); ohne Angabe gilt das vom Server gesetzte ``DATASETS``."""
    resolve = resolve or DATASETS
    lang = req.get("lang", "de")
    ctx = P.make_ctx(req.get("ctx") or {})
    view = req.get("view") or {}
    x0, x1 = float(view.get("xmin", -10)), float(view.get("xmax", 10))
    y0, y1 = float(view.get("ymin", -10)), float(view.get("ymax", 10))
    w = float(view.get("w") or 800)
    h = float(view.get("h") or 500)
    nfx = int(max(400, min(2400, 2 * w)))
    yspan = abs(y1 - y0)
    rows = [r for r in req.get("rows") or [] if r.get("id") is not None]
    out = {str(r["id"]): {"type": "empty"} for r in rows}
    deg = ctx.angle == "deg"

    # 1. Tabellen
    cols, data_of = {}, {}
    for r in rows:
        if r.get("kind") != "table":
            continue
        rid = str(r["id"])
        try:
            spec = r.get("table") or {}
            names, arrs = [], []
            for c in spec.get("cols") or []:
                nm = E.norm_name(c.get("name") or "")
                if nm in cols or nm in names:
                    raise E.CalcError(f"Spalte {nm} gibt es schon")
                vals = [_cell(v, ctx) for v in c.get("values") or []]
                names.append(nm)
                arrs.append(vals)
            m = max((len(a) for a in arrs), default=0)
            arrs = [np.array(a + [np.nan] * (m - len(a)), dtype=float) for a in arrs]
            for nm, a in zip(names, arrs):
                cols[nm] = a
                ctx.names[nm] = a
                ctx.dims.pop(nm, None)
            series = []
            if len(arrs) >= 2:
                for k in range(1, len(arrs)):
                    ok = np.isfinite(arrs[0]) & np.isfinite(arrs[k])
                    series.append({"col": k, "name": names[k], "x": arrs[0][ok].tolist(), "y": arrs[k][ok].tolist()})
            out[rid] = {"type": "table", "columns": names, "series": series}
            if len(arrs) >= 2:
                data_of[rid] = {"x": (names[0], arrs[0], "", names[0]),
                                "ys": [(names[k], arrs[k], "", names[k]) for k in range(1, len(arrs))], "title": ""}
        except _EVAL_ERR as e:
            out[rid] = {"type": "error", "error": str(e)}
    _dataset_rows(rows, out, cols, ctx, data_of, (x0, x1, y0, y1, w, h), resolve)          # G-01
    _fit_rows(rows, out, data_of, (x0, x1, y0, y1, w, h), nfx, yspan, req.get("ui_lang") or lang)   # G-02

    # 2. Zeilen lesen
    stmts = {}
    for r in rows:
        if r.get("kind") in ("table", "curve", "note", "dataset", "fit"):
            continue
        rid = str(r["id"])
        try:
            stmts[rid] = classify(r.get("src", ""))
        except E.CalcError as e:
            out[rid] = {"type": "error", "error": str(e)}
    func_names = {s[1] for s in stmts.values() if s[0] == "func"}
    def_names = [s[1] for s in stmts.values() if s[0] == "def"]
    dup = {n for n in def_names if def_names.count(n) > 1} | (func_names & set(def_names))
    callables = ctx.callables() | frozenset(func_names)
    for n in set(def_names) | func_names:
        ctx.names.pop(n, None)
        ctx.dims.pop(n, None)
    known0 = set(ctx.names) | set(def_names) | set(cols) | set(E.BUILTINS) | set(E.SPECIAL)

    # Regressionsparameter: freie Namen der Modelle
    params_of = {}
    for rid, s in stmts.items():
        if s[0] != "reg":
            continue
        try:
            _, fr, _ = _parse(s[2], callables, known0)
            _, fl, _ = _parse(s[1], callables, known0)
            params_of[rid] = sorted(fr - LOCALS - fl)
        except E.CalcError as e:
            out[rid] = {"type": "error", "error": str(e)}
    known = known0 | {p for ps in params_of.values() for p in ps}

    # 3. Ausdrücke parsen
    nodes = {}
    for rid, s in stmts.items():
        if out[rid].get("type") == "error":
            continue
        kind = s[0]
        try:
            if kind == "empty":
                continue
            if kind == "def":
                if s[1] in RESERVED or s[1] in U.CONSTANTS or s[1] in LOCALS - {"r"}:
                    raise E.CalcError(f"„{E.plain_name(s[1])}“ ist reserviert")
                if s[1] in dup:
                    raise E.CalcError(f"„{E.plain_name(s[1])}“ ist mehrfach definiert")
                node, free, used = _parse(s[2], callables, known)
                nodes[rid] = {"node": node, "free": free, "used": used,
                              "html": _html(R.sym_html(s[1]), "=", _r(node, lang) or "")}
            elif kind == "func":
                if s[1] in E.BUILTINS or s[1] in E.SPECIAL or s[1] in dup:
                    raise E.CalcError(f"„{s[1]}“ ist schon vergeben")
                node, free, used = _parse(s[3], callables, known | set(s[2]))
                ctx.funcs[s[1]] = (list(s[2]), node)
                nodes[rid] = {"node": node, "free": free, "used": used,
                              "html": _html(f"{s[1]}({', '.join(R.sym_html(a) for a in s[2])})", "=", _r(node, lang) or "")}
            elif kind in ("y", "x"):
                node, free, used = _parse(s[1], callables, known | {"x", "y"})
                nodes[rid] = {"node": node, "free": free, "used": used,
                              "html": _html(f"<i>{kind}</i>", "=", _r(node, lang) or "")}
            elif kind == "r":
                node, free, used = _parse(s[1], callables, known | {"theta"})
                nodes[rid] = {"node": node, "free": free, "used": used, "html": _html("<i>r</i>", "=", _r(node, lang) or "")}
            elif kind == "pair":
                a, fa, ua = _parse(s[1], callables, known | {"t"})
                b, fb, ub = _parse(s[2], callables, known | {"t"})
                nodes[rid] = {"node": (a, b), "free": fa | fb, "used": ua | ub,
                              "html": _html("(", _r(a, lang) or "", ",", _r(b, lang) or "", ")")}
            elif kind == "eq":
                a, fa, ua = _parse(s[1], callables, known | {"x", "y"})
                b, fb, ub = _parse(s[2], callables, known | {"x", "y"})
                nodes[rid] = {"node": ast.BinOp(left=a, op=ast.Sub(), right=b), "free": fa | fb, "used": ua | ub,
                              "html": _html(_r(a, lang) or "", "=", _r(b, lang) or "")}
            elif kind == "reg":
                a, fa, ua = _parse(s[1], callables, known)
                b, fb, ub = _parse(s[2], callables, known)
                nodes[rid] = {"node": (a, b), "free": (fa | fb), "used": ua | ub,
                              "html": _html(_r(a, lang) or "", "~", _r(b, lang) or "")}
            elif kind == "expr":
                node, free, used = _parse(s[1], callables, known | {"x"})
                nodes[rid] = {"node": node, "free": free, "used": used, "html": _r(node, lang)}
        except E.CalcError as e:
            out[rid] = {"type": "error", "error": str(e)}

    def free_error(rid, free):
        names = sorted(E.plain_name(f) for f in free)
        sug = [n for n in names if n not in LOCALS and n not in ("i", "j") and re.fullmatch(r"[^\W\d]\w*", n)]
        out[rid] = {"type": "error", "error": "Nicht definiert: " + ", ".join(names), "free": sug,
                    "html": nodes[rid].get("html")}

    # 4. Konstanten und Regressionen in passender Reihenfolge
    pending = [rid for rid, s in stmts.items() if rid in nodes and s[0] in ("def", "reg")]
    last_err = {}
    for _ in range(len(pending) + 2):
        progress = False
        for rid in list(pending):
            s, nd = stmts[rid], nodes[rid]
            try:
                if s[0] == "def":
                    if nd["free"] & {"x", "y"}:
                        pending.remove(rid)
                        out[rid] = {"type": "error", "html": nd.get("html"),
                                    "error": f"x und y gehören in eine Kurve: {E.plain_name(s[1])}(x) = … oder y = … schreiben"}
                        continue
                    if nd["free"]:
                        pending.remove(rid)
                        free_error(rid, nd["free"])
                        continue
                    val = E.evaluate(nd["node"], ctx)
                    if isinstance(val, str):
                        raise E.CalcError("Text ist hier kein Wert")
                    ctx.names[s[1]] = val
                    d = E.describe(val, 8)
                    slider = bool(NUM.match(s[2])) and d.get("type") == "scalar"
                    out[rid] = {"type": "slider" if slider else "value", "name": E.plain_name(s[1]),
                                "value": float(np.real(val)) if d.get("type") == "scalar" else None,
                                "text": d.get("text"), "html": nd["html"]}
                else:
                    params = params_of.get(rid, [])
                    a, b = nd["node"]
                    vals, r2, npts, info = regress(a, b, params, ctx)
                    ctx.names.update(vals)
                    out[rid] = {"type": "regression", "params": vals, "r2": r2, "n": npts, "html": nd["html"],
                                "param_text": {k: E.fmt_num(v, 6) for k, v in vals.items()},
                                "u": info["u"], "ci": info["ci"], "t": info["t"], "dof": info["dof"],
                                "converged": info["converged"],
                                "u_text": {k: (E.fmt_num(v, 2) if v is not None else None) for k, v in info["u"].items()},
                                "ci_text": {k: (E.fmt_num(v, 2) if v is not None else None) for k, v in info["ci"].items()}}
                    if not info["converged"]:
                        out[rid]["warn"] = ("Anpassung nicht konvergiert (Gradientenkriterium) – Werte unzuverlässig; "
                                            "Startwerte über Schieberegler oder anderes Modell versuchen")
                pending.remove(rid)
                progress = True
            except _EVAL_ERR as e:
                last_err[rid] = str(e)
        if not progress:
            break
    for rid in pending:
        out[rid] = {"type": "error", "error": last_err.get(rid, "Nicht berechenbar"), "html": nodes[rid].get("html")}

    # 5. Kurven, Punkte, Werte
    fx_fns = {}
    for rid, s in stmts.items():
        if rid not in nodes or s[0] in ("def",):
            continue
        nd = nodes[rid]
        kind = s[0]
        row = next(r for r in rows if str(r["id"]) == rid)
        try:
            if kind == "reg":
                if out[rid].get("type") != "regression":
                    continue
                a, b = nd["node"]
                xs = [c for c in cols if c in nd["used"] and c not in {n.id for n in ast.walk(a) if isinstance(n, ast.Name)}]
                if len(xs) == 1:
                    X = np.linspace(x0, x1, nfx)
                    Y = _vec(b, ctx, xs[0], X)
                    out[rid]["x"], out[rid]["y"] = P._breaks(X, Y, yspan)
                    fx_fns[rid] = (lambda node, var: lambda v: E.evaluate(node, ctx, {var: v}))(b, xs[0])
                continue
            if nd["free"] - ({"x", "y"} if kind in ("eq", "x", "y") else set()):
                free_error(rid, nd["free"] - ({"x", "y"} if kind in ("eq", "x", "y") else set()))
                continue
            if kind == "func":
                args = ctx.funcs[s[1]][0]
                if len(args) != 1:
                    out[rid] = {"type": "func", "html": nd["html"]}
                    continue
                X = np.linspace(x0, x1, nfx)
                Y = _vec(nd["node"], ctx, args[0], X)
                xs_, ys_ = P._breaks(X, Y, yspan)
                out[rid] = {"type": "curve", "x": xs_, "y": ys_, "fx": True, "html": nd["html"]}
                fx_fns[rid] = (lambda node, var: lambda v: E.evaluate(node, ctx, {var: v}))(nd["node"], args[0])
            elif kind in ("y", "expr") and "y" not in nd["used"]:
                if kind == "expr" and "x" not in nd["used"]:
                    val = E.evaluate(nd["node"], ctx)
                    d = E.describe(val, 8)
                    out[rid] = {"type": "value", "text": d.get("text"), "html": nd["html"],
                                "value": float(np.real(val)) if d.get("type") == "scalar" else None}
                    continue
                X = np.linspace(x0, x1, nfx)
                Y = _vec(nd["node"], ctx, "x", X)
                xs_, ys_ = P._breaks(X, Y, yspan)
                out[rid] = {"type": "curve", "x": xs_, "y": ys_, "fx": True, "html": nd["html"]}
                fx_fns[rid] = (lambda node: lambda v: E.evaluate(node, ctx, {"x": v}))(nd["node"])
            elif kind == "x" and "x" not in nd["used"]:
                Yg = np.linspace(y0, y1, nfx)
                Xg = _vec(nd["node"], ctx, "y", Yg)
                ys_, xs_ = P._breaks(Yg, Xg, abs(x1 - x0))
                out[rid] = {"type": "curve", "x": xs_, "y": ys_, "html": nd["html"]}
            elif kind in ("y", "x", "eq"):
                node = nd["node"]
                if kind != "eq":
                    node = ast.BinOp(left=ast.Name(id=kind, ctx=ast.Load()), op=ast.Sub(), right=node)
                if not ({"x", "y"} & nd["used"]) and kind == "eq":
                    raise E.CalcError("Gleichung ohne x und y – für einen Wert a = … schreiben")
                nx = int(max(80, min(260, w / 4)))
                ny = int(max(60, min(200, h / 4)))
                out[rid] = {"type": "implicit", "segs": contour(node, ctx, view, nx, ny), "html": nd["html"]}
            elif kind == "r":
                t0, t1 = _range(row, ctx, 0.0, 360.0 if deg else 2 * math.pi)
                T = np.linspace(t0, t1, 2000)
                Rr = _vec(nd["node"], ctx, "theta", T)
                th = T * ctx.aconv
                out[rid] = {"type": "curve", "x": _list(Rr * np.cos(th)), "y": _list(Rr * np.sin(th)),
                            "html": nd["html"], "trange": [t0, t1], "tvar": "θ"}
            elif kind == "pair":
                a, b = nd["node"]
                if "t" in nd["used"]:
                    t0, t1 = _range(row, ctx, 0.0, 360.0 if deg else 2 * math.pi)
                    T = np.linspace(t0, t1, 2000)
                    out[rid] = {"type": "curve", "x": _list(_vec(a, ctx, "t", T)), "y": _list(_vec(b, ctx, "t", T)),
                                "html": nd["html"], "trange": [t0, t1], "tvar": "t"}
                else:
                    with np.errstate(all="ignore"):
                        px = np.atleast_1d(np.asarray(np.real(E.evaluate(a, ctx)), dtype=float)).ravel()
                        py = np.atleast_1d(np.asarray(np.real(E.evaluate(b, ctx)), dtype=float)).ravel()
                    px, py = np.broadcast_arrays(px, py)
                    out[rid] = {"type": "points", "x": _list(px), "y": _list(py), "html": nd["html"]}
        except _EVAL_ERR as e:
            out[rid] = {"type": "error", "error": str(e), "html": nd.get("html")}

    res = {"rows": out}
    focus = str(req.get("focus") or "")
    if focus in fx_fns:
        res["poi"] = {"row": focus, "points": poi(focus, fx_fns, rows, x0, x1)}
    return res


def _list(a):
    return [E._jnum(v) for v in np.asarray(a, dtype=float)]


def _range(row, ctx, d0, d1):
    def num(v, d):
        if v is None or str(v).strip() == "":
            return d
        try:
            return float(str(v).replace(",", "."))
        except ValueError:
            return float(np.real(E.evaluate(E.parse(str(v), ctx.callables()), ctx)))
    return num(row.get("tmin"), d0), num(row.get("tmax"), d1)


def poi(rid, fns, rows, a, b):
    """Besondere Punkte einer Funktionskurve: Nullstellen, Extrema, y-Achsenabschnitt, Schnittpunkte."""
    f = fns[rid]

    def fv(t):
        return P.eval_vec(f, np.atleast_1d(np.asarray(t, dtype=float)))

    pts = [{"x": r, "y": 0.0, "kind": "root"} for r in P.roots_in(f, a, b)]
    pts += [{"x": e["x"], "y": e["y"], "kind": e["type"]} for e in P.extrema_in(f, a, b)]
    if a < 0 < b:
        y0 = float(fv(0.0)[0])
        if math.isfinite(y0):
            pts.append({"x": 0.0, "y": y0, "kind": "yint"})
    hidden = {str(r["id"]) for r in rows if r.get("hidden")}
    for oid, g in fns.items():
        if oid == rid or oid in hidden:
            continue
        h = (lambda f_, g_: lambda x: np.asarray(f_(x), dtype=float) - np.asarray(g_(x), dtype=float))(f, g)
        for r in P.roots_in(h, a, b):
            pts.append({"x": r, "y": float(fv(r)[0]), "kind": "int", "with": oid})
    return [p for p in pts if math.isfinite(p["y"])][:60]


# ----------------------------------------------------------------------------- Bild für den Bericht
def figure(plot: dict, ctx_req: dict, lang="de", curves=None):
    """Matplotlib-Bild der Ausdrucksliste plus Formelkurven; gibt (fig, Datenreihen für CSV) zurück."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    view = {**(plot.get("view") or {}), "w": 1400, "h": 900}
    res = compute({"rows": plot.get("rows") or [], "view": view, "ctx": ctx_req, "lang": lang})["rows"]
    fig, ax = plt.subplots(figsize=(6.4, 4.2))
    data = []
    for k, r in enumerate(plot.get("rows") or []):
        if r.get("hidden"):
            continue
        o = res.get(str(r.get("id"))) or {}
        col = r.get("color") or P.COLORS[k % len(P.COLORS)]
        label = (r.get("src") or "").strip().replace("$", r"\$")
        t = o.get("type")
        if t == "curve":
            ax.plot(P._nan(o["x"]), P._nan(o["y"]), "-", lw=1.6, color=col, label=label)
            data.append({"label": label, "x": o["x"], "y": o["y"]})
        elif t == "regression" and o.get("x"):
            pt = "; ".join(f"{E.plain_name(p)} = {v if lang == 'en' else str(v).replace('.', ',')}" for p, v in (o.get("param_text") or {}).items())
            r2 = f"{o['r2']:.4f}".replace(".", "," if lang == "de" else ".")
            ax.plot(P._nan(o["x"]), P._nan(o["y"]), "-", lw=1.4, color=col, label=f"{label}  ({pt}; R² = {r2})")
            data.append({"label": label, "x": o["x"], "y": o["y"]})
        elif t == "implicit" and o.get("segs"):
            segs = [[(s[0], s[1]), (s[2], s[3])] for s in o["segs"]]
            ax.add_collection(LineCollection(segs, colors=col, linewidths=1.6, label=label))
        elif t == "points":
            ax.plot(o["x"], o["y"], "o", ms=5, color=col, label=label)
            data.append({"label": label, "x": o["x"], "y": o["y"], "points": True})
        elif t == "table":
            for s in o.get("series") or []:
                c2 = col if s["col"] == 1 else P.COLORS[(k + s["col"]) % len(P.COLORS)]
                many = len(s["x"]) > 5000
                if s.get("line"):
                    ax.plot(P._nan(s["x"]), P._nan(s["y"]), "-", lw=1.1, color=c2, label=f"{o['columns'][0]}, {s['name']}",
                            rasterized=many)
                else:
                    ax.plot(P._nan(s["x"]), P._nan(s["y"]), "o", ms=2.2 if len(s["x"]) > 400 else 4.5, color=c2,
                            label=f"{o['columns'][0]}, {s['name']}", rasterized=many)
                data.append({"label": s["name"], "x": s["x"], "y": s["y"], "points": not s.get("line"),
                             "columns": [o["columns"][0], s["name"]], "thinned": s.get("n", 0) > s.get("sent", 0)})
        elif t == "fit" and o.get("x"):
            r2 = f"{o['r2']:.4f}".replace(".", "," if lang == "de" else ".") if o.get("r2") is not None else "–"
            ax.plot(P._nan(o["x"]), P._nan(o["y"]), "-", lw=1.5, color=col, label=f"{o.get('name')} ({o.get('yname')}), R² = {r2}")
            data.append({"label": o.get("name") or "fit", "x": o["x"], "y": o["y"]})
    for c in curves or []:
        ax.plot(P._nan(c["x"]), P._nan(c["y"]), "-", lw=1.6, color=c.get("color") or "#37474f", label=c.get("label"))
    v = plot.get("view") or {}
    if any(not r.get("hidden") for r in plot.get("rows") or []) or not curves:
        ax.set_xlim(float(v.get("xmin", -10)), float(v.get("xmax", 10)))
        ax.set_ylim(float(v.get("ymin", -6)), float(v.get("ymax", 6)))
        ax.axhline(0, color="#90a4ae", lw=0.8, zorder=0)
        ax.axvline(0, color="#90a4ae", lw=0.8, zorder=0)
    ax.grid(True, color="#e0e0e0", lw=0.6)
    ax.set_xlabel(plot.get("xlabel") or "x")
    ax.set_ylabel(plot.get("ylabel") or "y")
    if ax.get_legend_handles_labels()[0]:
        ax.legend(fontsize=8, loc="best")
    if lang == "de":
        from matplotlib.ticker import FuncFormatter
        fmt = FuncFormatter(lambda val, _p: f"{val:g}".replace(".", ","))
        ax.xaxis.set_major_formatter(fmt)
        ax.yaxis.set_major_formatter(fmt)
    fig.tight_layout()
    return fig, data, res
