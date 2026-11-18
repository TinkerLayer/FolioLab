"""Lokale Oberfläche des Elementrechners.

Läuft nur auf 127.0.0.1. Das Netz wird nur auf ausdrücklichen Knopfdruck benutzt (Name eines gezeichneten Moleküls
bei PubChem nachschlagen; gesendet wird nur die Struktur). Geschrieben wird nur in die eigenen Stoffe
(<ausgaben>/eigene_stoffe.json). Datensätze anderer Module (DP-12, /api/dataset) werden nur gelesen.

Start:  python -m elementrechner.server  [--port 8769] [--out Ausgaben] [--no-browser]
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import threading
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

_SDK = Path(__file__).resolve().parents[3] / "sdk" / "python"
if _SDK.is_dir() and str(_SDK) not in sys.path:
    sys.path.insert(0, str(_SDK))

import labcite  # noqa: E402
from labcalc import chem as C  # noqa: E402
from labcalc import expr as _E  # noqa: E402,F401 - meldet M(), pKa() … und den Namensauflöser an
from labcalc import substances as S  # noqa: E402
from labuser import JsonStore  # noqa: E402

from . import __version__  # noqa: E402
from . import analysis as AN  # noqa: E402
from . import ptable as PT  # noqa: E402
from .refs import REFS  # noqa: E402

STATIC = Path(__file__).resolve().parent / "static"
ROOT = Path(__file__).resolve().parents[1]
ORIGIN_OK = re.compile(r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$")
MAX_BODY = 20 * 1024 * 1024
MIME = {".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml",
        ".png": "image/png", ".txt": "text/plain; charset=utf-8", ".json": "application/json; charset=utf-8"}


class State:
    def __init__(self, out_root: Path):
        self.out_root = out_root
        self.own = JsonStore(out_root / "eigene_stoffe.json", kind="folio-stoffe/1")
        S.set_user_store(self.own_records)
        from labproject import ModuleEnvs
        self.envs = ModuleEnvs(out_root, "elementrechner")   # A2: Arbeitsstand je Umgebung, keine Dateien

    def own_records(self) -> dict:
        """Eigene Stoffe im Format der Sammlung, Schlüssel „own:<id>“."""
        out = {}
        for it in self.own.items():
            out["own:" + it["id"]] = {
                "own": True, "id": it["id"], "name": it.get("name"), "en": it.get("name_en") or it.get("name"),
                "de": it.get("name"), "formula": it.get("formula") or None, "smiles": it.get("smiles") or None,
                "cas": it.get("cas") or None, "kind": it.get("kind") or ("molecule" if it.get("smiles") else "mixture"),
                "classes": ["Eigene Stoffe | Own substances"] + [c for c in it.get("classes", []) if c],
                "syn_de": [s for s in it.get("synonyms", []) if s], "note": it.get("note", ""),
                "source": it.get("source"), "values": it.get("values") or {}, "changed": it.get("changed"),
                "ref": it.get("ref") or None}
        return out


THERMO_KEYS = ("dfH", "dfG", "S0", "Cp")   # kJ/mol, kJ/mol, J/(mol·K), J/(mol·K) bei 298,15 K
OWN_KEYS = {"id", "name", "name_en", "formula", "smiles", "molfile", "cas", "kind", "classes", "synonyms", "note",
            "source", "values", "ref"}


def own_clean(item: dict) -> dict:
    """Eigenen Stoff prüfen: Name Pflicht; Formel (falls angegeben) muss lesbar sein; Werte mit Quelle."""
    it = {k: v for k, v in (item or {}).items() if k in OWN_KEYS}
    it["name"] = str(it.get("name") or "").strip()[:120]
    if not it["name"]:
        raise ValueError("Name fehlt")
    if it.get("formula"):
        it["formula"] = str(it["formula"]).strip()[:120]
        C.parse_species(it["formula"])
    if it.get("smiles") and len(str(it["smiles"])) > 4000:
        raise ValueError("SMILES zu lang")
    vals = {}
    for k, lst in (it.get("values") or {}).items():
        if k not in S.PROPS and k not in ("pka",) + THERMO_KEYS:
            continue
        out = []
        for v in lst or []:
            try:
                num = float(v["v"])
            except (KeyError, TypeError, ValueError):
                continue
            src = v.get("source") if isinstance(v.get("source"), dict) else None
            row = {"v": num, "u": str(v.get("u") or ""), "T": float(v["T"]) if v.get("T") not in (None, "") else None,
                   "txt": str(v.get("txt") or "")[:200], "source": src, "src": "own"}
            if v.get("est"):                           # Schätzwert aus dem Moleküldesigner (Verfahren in "method")
                row["est"] = True
                row["method"] = str(v.get("method") or "")[:120]
            if k in THERMO_KEYS:                       # Bildungsgrössen gelten für eine Phase (cr, l, g, aq)
                ph = str(v.get("phase") or "").strip()
                row["phase"] = ph if ph in ("cr", "l", "g", "aq", "s") else ""
            out.append(row)
        if out:
            vals[k] = out
    it["values"] = vals
    return it


STATE: State | None = None


def clean(o):
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items() if not str(k).startswith("_")}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, float):
        return o if math.isfinite(o) else None
    if hasattr(o, "numerator") and hasattr(o, "denominator") and not isinstance(o, (int, bool)):
        return float(o)
    return o


def meta_payload() -> dict:
    try:
        aw = C.atomic_weights()
    except C.ChemError as e:                    # Daten noch nicht eingespielt: Seite zeigt den Hinweis
        aw = {"_missing": str(e)}
    els = []
    for d in PT.table():
        w = aw.get(d["symbol"]) or {}
        els.append({**d, "Ar": w.get("value"), "Ar_text": w.get("text"), "mass_number": w.get("mass_number")})
    return {"version": __version__, "elements": els, "refs": {k: {"short": v.get("short") or labcite.short(v), "text": labcite.text(v)}
                                                               for k, v in REFS.items()},
            "atomic_weights_source": aw.get("_source"), "data_missing": aw.get("_missing")}


class Handler(BaseHTTPRequestHandler):
    server_version = "FolioElementrechner/0.1"

    def log_message(self, fmt, *args):
        pass

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200):
        self._send(code, json.dumps(clean(obj), ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _req(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_BODY:
            raise ValueError("Anfrage zu gross")
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def do_GET(self):
        url = urlparse(self.path)
        p = url.path
        if p in ("/", "/index.html"):
            return self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
        if p in ("/labref.js", "/labenv.js", "/labindex.js", "/labui.js", "/labboard.js", "/labimport.js"):   # I-02
            return self._send(200, labcite.web_asset(p[1:]), "text/javascript; charset=utf-8")
        if p.startswith("/static/"):
            f = (STATIC / p[len("/static/"):]).resolve()
            if STATIC.resolve() in f.parents and f.is_file():
                return self._send(200, f.read_bytes(), MIME.get(f.suffix, "application/octet-stream"))
        if p == "/api/meta":
            return self._json(meta_payload())
        self._send(404, b"nicht gefunden", "text/plain")

    def do_POST(self):
        url = urlparse(self.path)
        origin = self.headers.get("Origin")
        if origin and not ORIGIN_OK.match(origin):
            return self._json({"error": "Fremde Herkunft abgelehnt"}, 403)
        try:
            return self._route(url.path)
        except (C.ChemError, ValueError) as e:
            return self._json({"error": str(e)}, 400)
        except LookupError as e:
            return self._json({"error": str(e).strip("'\"")}, 404)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            return self._json({"error": f"{type(e).__name__}: {e}"}, 500)

    def _route(self, p):
        if p.startswith("/api/env/"):
            return self._json(STATE.envs.route(p.rsplit("/", 1)[1], self._req(), list))
        if p.startswith("/api/index/"):                # A7: Projektindex
            import labindex
            return self._json(labindex.route(STATE.envs, "elementrechner", __version__, p.rsplit("/", 1)[1], self._req()))
        if p.startswith("/api/prov/"):                 # A8: Herkunftskette, Abhängigkeiten
            import labprov
            return self._json(labprov.route(STATE.envs, p.rsplit("/", 1)[1], self._req()))
        if p.startswith("/api/share/"):                # A3: geteilte TGA-Stufen (nur lesen; Kopie liegt im Seitenzustand)
            from . import shared as SH
            req, act = self._req(), p.rsplit("/", 1)[1]
            if act == "list":
                return self._json({"shares": SH.list_shares(STATE.envs, req.get("kind") or SH.KIND)})
            if act == "board":                         # UI-11: Kästen der Übersicht
                return self._json(SH.board_shares(STATE.envs))
            if act == "ir":                            # A6: Struktur gegen geteilte FTIR-Banden
                env = req.get("envelope") or SH.get_share(STATE.envs, req.get("id") or "", req.get("version"))
                return self._json(SH.compare_ir(env, req.get("smiles") or ""))
            if act == "get":
                return self._json(SH.get_share(STATE.envs, req.get("id") or "", req.get("version")))
            if act == "values":
                return self._json(SH.publish_values(STATE.envs, req.get("items") or [], __version__))
            if act == "envvalues":                     # UI-15: Werte an andere Umgebungen
                return self._json(SH.publish_env_values(STATE.envs, str(req.get("env") or ""), req.get("items") or [], __version__))
            if act == "resolve":
                return self._json(SH.resolve(STATE.envs, req.get("binding") or {}))
            if act == "compare":
                env = req.get("envelope") or SH.get_share(STATE.envs, req.get("id") or "", req.get("version"))
                return self._json({"rows": SH.compare(env, req.get("rows") or [])})
            if act == "theory":
                return self._json(SH.theoretical_loss(req.get("equation") or "", req.get("basis") or ""))
            return self._json({"error": "unbekannt"}, 404)
        if p == "/api/dataset":                        # DP-12: Messreihen aus einem Datensatz der Datenaufbereitung
            from . import datasets as DSET
            return self._json(DSET.route(STATE.envs, self._req()))
        if p == "/api/run":
            return self._json(AN.run(self._req().get("state") or {}))
        if p == "/api/chain":                          # UI-12: Reaktionskette einer Umgebung
            from . import chain as CH
            r = self._req()
            return self._json(CH.analyse(r.get("steps") or [], r.get("feeds") or {}, r.get("target") or None))
        if p == "/api/species":
            return self._json(AN.species_card(self._req().get("formula") or ""))
        if p == "/api/element":
            info = C.element_info(self._req().get("symbol") or "")
            if info.get("Z"):                                             # ER-X02: alle Ionisierungsenergien (NIST ASD)
                from labcalc import ionization as IO
                info["ie_series"] = IO.series(info["Z"])
                from labcalc import radii as RA
                info["radii"] = RA.for_element(info.get("symbol") or "")
            return self._json(info)
        if p in ("/api/bundle", "/api/bundle/rebuild"):
            from . import bundle as B
            req = self._req()
            if p.endswith("rebuild"):
                src = (req.get("source") or {}).get("request") or {}
                req = {**src, **{k: v for k, v in req.items() if k != "source"}}
            return self._json(B.build(req, lang=req.get("lang") or "de"))
        if p == "/api/search":
            r = self._req()
            return self._json({"hits": S.find(str(r.get("q") or ""), int(r.get("limit") or 60), r.get("cls") or None),
                               "classes": S.collection().get("classes", []) + ["Eigene Stoffe | Own substances"]})
        if p == "/api/substance":
            r = self._req()
            key = r.get("key") or S.resolve(str(r.get("q") or ""))
            m = S.get(key) if key else None
            if not m:
                raise LookupError(f"„{r.get('q') or key}“ ist nicht in der Sammlung")
            out = {"substance": m, "props": S.properties(key), "pka": S.pka_values(key)["values"]}
            if m.get("formula"):
                try:
                    out["ksp"] = S.ksp_values(m["formula"])["values"]
                except C.ChemError:
                    out["ksp"] = []
            return self._json(out)
        if p == "/api/lookup":
            return self._json(lookup(self._req()))
        if p.startswith("/api/own/"):
            return self._own(p[len("/api/own/"):])
        if p == "/api/equilibrium":
            return self._json(AN.equilibrium_call(self._req()))
        if p == "/api/vapor":
            return self._json(AN.vapor_call(self._req()))
        if p == "/api/saturation":
            return self._json(AN.saturation_call(self._req()))
        if p == "/api/speciation":
            return self._json(AN.speciation_call(self._req()))
        if p.startswith("/api/kinetics/") and p[len("/api/kinetics/"):] in AN.KIN_KINDS:
            return self._json(AN.kinetics_call(p[len("/api/kinetics/"):], self._req()))
        if p.startswith("/api/nuclear/") and p[len("/api/nuclear/"):] in AN.NUC_KINDS:
            return self._json(AN.nuclear_call(p[len("/api/nuclear/"):], self._req()))
        if p.startswith("/api/prep/") and p[len("/api/prep/"):] in AN.PREP_KINDS:
            return self._json(AN.prep_call(p[len("/api/prep/"):], self._req()))
        if p == "/api/constants":                      # UI-13: Konstanten mit Quelle (CODATA 2022, SI-Broschüre)
            from labcalc import units as UN
            return self._json({"constants": UN.constants_list()})
        if p == "/api/indicators":
            from labcalc import acidbase as AB
            r = self._req()
            pH = r.get("pH")
            return self._json({"indicators": AB.indicators(), "meta": AB._indicator_data()["_meta"],
                               "colours": AB.indicator_colours(float(pH)) if pH is not None else None})
        if p in ("/api/ph", "/api/titration", "/api/buffer", "/api/buffers"):
            from labcalc import acidbase as AB
            r = self._req()
            T = float(r.get("T") or 25)
            act = r.get("activity") if r.get("activity") in ("davies", "edh") else None   # ER-S01, aus per Vorgabe
            if p == "/api/ph":
                out = AB.ph(str(r.get("mixture") or ""), T)
                if act:
                    from labcalc import activity as ACT
                    out["activity"] = ACT.ph_corrected(str(r.get("mixture") or ""), T, act)
                return self._json(out)
            if p == "/api/titration":
                return self._json(AB.titration(str(r.get("analyte") or ""), float(r.get("V0") or 25),
                                               str(r.get("titrant") or ""), float(r.get("c") or 0.1),
                                               float(r.get("Vmax") or 50), T_C=T))
            if p == "/api/buffer":
                out = AB.buffer(str(r.get("q") or ""), float(r.get("pH") or 7), float(r.get("c") or 0.1), T_C=T)
                if act:
                    from labcalc import activity as ACT
                    out["activity"] = ACT.buffer_corrected(out, act)
                return self._json(out)
            return self._json({"hits": AB.buffer_suggestions(float(r.get("pH") or 7))})
        if p == "/api/design/analyze":
            from . import design as D
            return self._json(D.analyze(str(self._req().get("smiles") or "")))
        if p == "/api/design/pubchem":                 # Netz nur auf Knopfdruck; gesendet wird nur die Struktur
            from . import design as D
            return self._json(D.pubchem(str(self._req().get("smiles") or "")))
        return self._send(404, b"nicht gefunden", "text/plain")

    def _own(self, op):
        r = self._req()
        if op == "list":
            return self._json({"items": STATE.own.items()})
        if op == "save":
            it = STATE.own.put(own_clean(r.get("item") or {}))
            S.set_user_store(STATE.own_records)
            return self._json({"item": it, "key": "own:" + it["id"]})
        if op == "delete":
            ok = STATE.own.delete(str(r.get("id") or ""))
            S.set_user_store(STATE.own_records)
            return self._json({"deleted": ok})
        if op == "export":
            return self._json(STATE.own.export())
        if op == "table":                                              # ER-X04: CSV/JSON-Tabelle mit Quellenpflicht
            from . import tables as TB
            rows, tsrc = TB.parse(str(r.get("text") or ""), str(r.get("format") or ""))
            items, errors = TB.to_items(rows, tsrc, STATE.own.items())
            ok = []
            for it in items:
                try:
                    ok.append(own_clean(it))
                except ValueError as e:
                    errors.append({"row": None, "error": f"{it.get('name')}: {e}"})
            bad = {it.get("name") for it in items} - {it["name"] for it in ok}
            n_vals = sum(1 for x in rows if (x.get("name") or "").strip() not in bad) - len([e for e in errors if e["row"]])
            if not r.get("dry"):
                for it in ok:
                    STATE.own.put(it)
                S.set_user_store(STATE.own_records)
            return self._json({"rows": len(rows), "substances": [it["name"] for it in ok], "values": n_vals,
                               "rejected": errors, "table_source": tsrc, "saved": not r.get("dry")})
        if op == "table_export":
            from . import tables as TB
            return self._json({"csv": TB.export_csv(STATE.own.items())})
        if op == "import":
            items = (r.get("data") or {}).get("items") if isinstance(r.get("data"), dict) else r.get("data")
            n = STATE.own.import_([own_clean(x) for x in (items or [])], replace=bool(r.get("replace")))
            S.set_user_store(STATE.own_records)
            return self._json({"imported": n})
        return self._send(404, b"nicht gefunden", "text/plain")


def lookup(r: dict) -> dict:
    """Nachschlagewerte mit allen Quellen; „choice“ ist der Vorschlag nach substances.choose."""
    kind = r.get("kind")
    q = str(r.get("q") or "")
    T = float(r.get("T") or 25)
    if kind == "pka":
        res = S.pka_values(q)
        steps = sorted({v["step"] for v in res["values"] if v.get("step")})
        res["choice"] = {str(s): S.choose([v for v in res["values"] if v.get("step") == s], T) for s in steps}
        return res
    if kind == "pkb":
        try:
            return {"query": q, "choice": S.pkb(q, int(r.get("step") or 1), T)}
        except C.ChemError as e:
            return {"query": q, "choice": None, "error": str(e)}
    if kind == "ksp":
        res = S.ksp_values(q)
        try:
            res["choice"] = S.ksp(q, T)
        except C.ChemError:
            res["choice"] = None
        return res
    if kind == "logk":
        res = S.logk_values(str(r.get("metal") or ""), str(r.get("ligand") or ""))
        ns = sorted({v["n"] for v in res["values"] if v.get("n")})
        res["choice"] = {str(n): S.choose([v for v in res["values"] if v.get("n") == n], T) for n in ns}
        return res
    if kind == "props":
        return S.properties(q)
    raise ValueError("unbekannte Art der Abfrage")


def main(argv=None):
    global STATE
    ap = argparse.ArgumentParser(description="Elementrechner, lokale Oberfläche")
    ap.add_argument("--port", type=int, default=8769)
    ap.add_argument("--out", default=str(ROOT / "Ausgaben"), help="Ordner für eigene Stoffe")
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args(argv)
    STATE = State(Path(a.out).resolve())
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    url = f"http://127.0.0.1:{a.port}/"
    print(f"Elementrechner läuft auf {url}  (Beenden mit Strg+C)")
    if not a.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
