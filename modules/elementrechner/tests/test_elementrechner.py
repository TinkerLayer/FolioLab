"""Tests des Elementrechners (Phase 1).

Die Atomgewichte hier sind ein kleiner Testsatz (gekürzte Werte, nur für die Tests); die echten Daten liegen in
sdk/python/labcalc/data/atomic_weights.json.

    python -m unittest discover -s tests      (im Ordner modules/elementrechner)
"""
from __future__ import annotations

import base64
import json
import sys
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parents[1] / "sdk" / "python"))

from labcalc import chem as C  # noqa: E402

from elementrechner import analysis as AN  # noqa: E402
from elementrechner import bundle as B  # noqa: E402
from elementrechner import ptable as PT  # noqa: E402
from elementrechner import server as SV  # noqa: E402

AW = {"H": (1.0080, 0.0002), "C": (12.011, 0.002), "N": (14.007, 0.001), "O": (15.999, 0.001), "S": (32.06, 0.02),
      "Cl": (35.45, 0.01), "K": (39.098, 0.001), "Mn": (54.938, 0.001), "Na": (22.990, 0.001), "Cu": (63.546, 0.003),
      "Fe": (55.845, 0.002)}
_TMP = TemporaryDirectory()
_OLD = None


# Kleine Test-Sammlung im Format von molecules.json / stability.json / pka.json / physprops.json (Werte nur für Tests)
MOLS = {"classes": ["Säuren | Acids", "Salze | Salts"], "molecules": {
    "QTBSBXVTEAMEQO-UHFFFAOYSA-N": {"cid": 176, "en": "acetic acid", "de": "Essigsäure", "formula": "C2H4O2",
                                    "hill": "C2H4O2", "smiles": "CC(=O)O", "cas": "64-19-7", "cls": [0], "syn": ["ethanoic acid"]},
    "HKZLPVFGJNLROG-UHFFFAOYSA-M": {"cid": 24470, "en": "silver chloride", "de": "Silberchlorid", "formula": "AgCl",
                                    "hill": "AgCl", "smiles": "[Cl-].[Ag+]", "cls": [1]},
    "poly:pe": {"en": "Polyethylene", "de": "Polyethylen", "formula": None, "repeat_unit": "C2H4", "kind": "polymer",
                "smiles": "*CC*", "cls": []}}}
SRD = {"ligands": {"1": {"name": "Acetic acid", "fig": "HL", "L": "C2H3O2", "Lq": -1, "class": "29",
                         "key": "QTBSBXVTEAMEQO-UHFFFAOYSA-N"},
                   "2": {"name": "Chloride ion", "fig": "L/-", "L": "Cl", "Lq": -1, "class": "54"}},
       "metals": {"68": {"name": "H⁺", "formula": "H", "charge": 1}, "2": {"name": "Ag⁺", "formula": "Ag", "charge": 1}},
       "defs": {"10": "[HL]/[H][L]", "20": "[M][L]/[ML(s)]", "30": "[ML]/[M][L]"},
       "rows": [["1", "68", "10", "K", "25", "0.0", 4.757, 0.002, None, None],
                ["1", "68", "10", "K", "25", "0.1", 4.56, None, None, None],
                ["2", "2", "20", "K", "25", "0.0", -9.75, 0.03, None, None],
                ["2", "2", "30", "K", "25", "0.0", 3.31, None, None, None]],
       "ksp": {"AgCl": [[2, 0, True]]}, "pair_lit": {}, "literature": {}}
PKA = {"compounds": {"x1": {"inchi": "InChI=1S/C2H4O2/c1-2(3)4/h1H3,(H,3,4)", "smiles": "CC(=O)O", "names": [],
                            "key": "QTBSBXVTEAMEQO-UHFFFAOYSA-N"}},
       "rows": [["x1", "pKa1", 4.75, 25.0, "Reliable", "E1a", "H1", "serjeant", None, None, "A", None]],
       "by_key": {"QTBSBXVTEAMEQO-UHFFFAOYSA-N": ["x1"]}, "methods": {}, "refs": {}}
PHYS = {"sources": {"icsc": {"name": "ICSC", "licence": "CC BY 4.0"}},
        "props": {"QTBSBXVTEAMEQO-UHFFFAOYSA-N": {"bp": [{"txt": "118 °C", "src": "icsc", "v": 118.0, "u": "°C"}],
                                                  "density": [{"txt": "1.05", "src": "icsc", "v": 1.049, "u": "g/cm³"}]}}}


# Bildungsdaten (Werte aus den CODATA Key Values, nur drei Stoffe für die Tests)
THERMO = {"refS": {"H": 65.34, "O": 102.576},
          "species": [{"src": "codata", "f": "H2", "ph": "g", "H": 0.0, "S": 130.68, "uS": 0.003, "hill": "H2", "q": 0},
                      {"src": "codata", "f": "O2", "ph": "g", "H": 0.0, "S": 205.152, "uS": 0.005, "hill": "O2", "q": 0},
                      {"src": "codata", "f": "H2O", "ph": "l", "H": -285.83, "uH": 0.04, "S": 69.95, "uS": 0.03,
                       "G": -237.14, "Gcalc": True, "hill": "H2O", "q": 0},
                      {"src": "codata", "f": "H2O", "ph": "g", "H": -241.826, "uH": 0.04, "S": 188.835, "uS": 0.01,
                       "G": -228.582, "Gcalc": True, "hill": "H2O", "q": 0}]}


def _clear_caches():
    from labcalc import substances as S
    from labcalc import thermo as TH
    C._json.cache_clear()
    for f in (S._index_build, S._srd_by_ligand, S._pka_by_cid, TH.data, TH._index):
        f.cache_clear()


def setUpModule():
    global _OLD
    p = Path(_TMP.name)
    (p / "atomic_weights.json").write_text(json.dumps({**{k: {"value": v, "u": u} for k, (v, u) in AW.items()},
                                                       "_source": "test"}), encoding="utf-8")
    for name, obj in (("molecules.json", MOLS), ("stability.json", SRD), ("pka.json", PKA), ("physprops.json", PHYS),
                      ("thermo.json", THERMO)):
        (p / name).write_text(json.dumps(obj), encoding="utf-8")
    _OLD = C.DATA
    C.DATA = p
    _clear_caches()


def tearDownModule():
    C.DATA = _OLD
    _clear_caches()
    _TMP.cleanup()


def files(d):
    return {k: base64.b64decode(v).decode("utf-8") for k, v in d["files"].items() if k.endswith(".tex")}


class PeriodicTable(unittest.TestCase):
    def test_positions(self):
        self.assertEqual(PT.position(1)["col"], 1)
        self.assertEqual(PT.position(2)["col"], 18)
        self.assertEqual(PT.position(72)["group"], 4)            # Hf nach den Lanthanoiden
        self.assertEqual(PT.position(57)["row"], 9)              # La in der Lanthanoidenzeile
        self.assertEqual(len(PT.table()), 118)


class Analysis(unittest.TestCase):
    def test_molar_mass(self):
        d = AN.species_card("H2SO4")
        self.assertAlmostEqual(d["molar_mass"]["M"], 2 * 1.008 + 32.06 + 4 * 15.999, places=6)
        self.assertEqual(d["hill"], "H2O4S")

    def test_stoich_limiting_and_yield(self):
        r = AN.equation_result("C3H8 + O2 -> CO2 + H2O", {"0": {"mass_g": 10}, "1": {"mass_g": 20}}, {"2": {"mass_g": 15}})
        st = r["stoich"]
        self.assertEqual(st["limiting"], 1)                      # O2
        self.assertAlmostEqual(st["extent"], 20 / 31.998 / 5, places=9)
        self.assertAlmostEqual(st["rows"][2]["yield_pct"], 100 * (15 / 44.009) / (3 * st["extent"]), places=6)

    def test_thermo_in_equation(self):
        r = AN.equation_result("H2 + O2 -> H2O", {"0": {"mass_g": 4.032}}, None, {"T": 400})
        th = r["thermo"]
        self.assertAlmostEqual(th["dH"], -571.66, places=2)
        self.assertEqual(th["rows"][2]["ph"], "l")                          # stabile Phase bei 298 K
        self.assertIn("(l) angenommen", th["rows"][2]["phase_note"])
        self.assertAlmostEqual(th["heat"]["Q_kJ"], -571.66, places=1)                 # 2 mol H2: ξ = 1 mol
        self.assertTrue(th["approx_T"])
        self.assertTrue(th["curve"])
        r = AN.equation_result("H2 + O2 -> H2O(g)", None, None, {"choices": {}})
        self.assertAlmostEqual(r["thermo"]["dH"], -483.652, places=3)
        # Datensatz wählen: Index 2 auf den Eintrag für Wasserdampf
        gid = next(a["id"] for a in AN.equation_result("H2 + O2 -> H2O")["thermo"]["rows"][2]["alternatives"] if a["ph"] == "g")
        r = AN.equation_result("H2 + O2 -> H2O", None, None, {"choices": {"2": gid}})
        self.assertAlmostEqual(r["thermo"]["dH"], -483.652, places=3)

    def test_run_collects_errors(self):
        out = AN.run({"equation": "Xx + O2 -> ", "species": ["H2O", "Qq"]})
        self.assertTrue(out["errors"])
        self.assertIn("error", out["species"][1])


class LatexOut(unittest.TestCase):
    def test_species_latex(self):
        self.assertEqual(C.parse_species("SO4^2-").latex(), r"\mathrm{SO_{4}}^{2-}")
        self.assertEqual(C.parse_species("CuSO4.5H2O").latex(), r"\mathrm{CuSO_{4}\cdot 5\,H_{2}O}")
        self.assertEqual(C.parse_species("^13CO2").latex(), r"\mathrm{{}^{13}CO_{2}}")
        self.assertEqual(C.parse_species("H2O(l)").latex(), r"\mathrm{H_{2}O}\,(\mathrm{l})")

    def test_equation_latex_without_packages(self):
        r = C.balance(C.parse_equation("H2 + O2 -> H2O"))
        self.assertEqual(r["latex"], r"2\,\mathrm{H_{2}} + \mathrm{O_{2}} \longrightarrow 2\,\mathrm{H_{2}O}")
        for bad in ("\\ce{", "\\tfrac", "\\boldsymbol", "\\text{"):
            self.assertNotIn(bad, r["latex"])


class Bundle(unittest.TestCase):
    def test_full_bundle(self):
        d = B.build({"state": {"equation": "C3H8 + O2 -> CO2 + H2O", "amounts": {"0": {"mass_g": 10}},
                               "species": ["CuSO4·5H2O"]}}, lang="de")
        self.assertEqual(d["format"], "folio-lab-bundle/1")
        tex = files(d)
        self.assertIn(r"\longrightarrow", tex["text-gleichung.tex"])
        allt = "\n".join(tex.values())
        for bad in ("\\ce{", "\\tfrac", "\\boldsymbol", "\\text{"):     # Vorlage lädt weder mhchem noch amsmath
            self.assertNotIn(bad, allt)
        keys = {i["key"] for i in d["items"] if i["kind"] == "citation"}
        self.assertTrue({"er-ciaaw2021", "er-trost1991"} <= keys)
        self.assertIn("molmasse-cuso45h2o", tex["values.tex"])
        self.assertIn("{masse-co2}", tex["values.tex"])
        # Neuaufbau aus der gespeicherten Quelle liefert dasselbe
        d2 = B.build(d["source"]["request"], lang="en")
        self.assertIn("balanced by conserving", files(d2)["text-gleichung.tex"])
        self.assertEqual(files(d2)["text-gleichung.tex"].split("\n")[0], tex["text-gleichung.tex"].split("\n")[0])

    def test_unbalanceable_and_empty(self):
        d = B.build({"state": {"equation": "NaCl -> Na + Cl2 + K"}})
        self.assertIn("nur rechts", files(d)["text-gleichung.tex"])
        with self.assertRaises(ValueError):
            B.build({"state": {}})

    def test_thermo_bundle(self):
        d = B.build({"state": {"equation": "H2 + O2 -> H2O", "amounts": {"0": {"mass_g": 4.032}}, "thermo": {"T": 500}}})
        tex = files(d)
        t = tex["text-thermochemie.tex"]
        self.assertIn(r"\Delta_\mathrm{r}H^\circ = \sum_i", t)                 # Hess-Summe mit eingesetzten Werten
        self.assertIn("-571{,}66", t)
        self.assertIn("Aktivierungsenergie folgt nicht", t)
        self.assertIn(r"$T = 500{,}00$\,K gilt genähert", t)     # Testdaten ohne Cp: Näherung (Cp-Modell: test_thermo_t)
        self.assertIn("thermochemie.tex", tex)
        self.assertIn("fig/dg-t.pdf", d["files"])
        for k in ("{dH-r}", "{dS-r}", "{dG-r}", "{K-298}", "{lgK-298}", "{T-star}", "{Q-r}"):
            self.assertIn(k, tex["values.tex"])
        keys = {i["key"] for i in d["items"] if i["kind"] == "citation"}
        self.assertIn("er-cox1989", keys)
        self.assertIn("er-atkins", keys)
        d = B.build({"state": {"equation": "H2 + O2 -> H2O"}}, lang="en")
        self.assertIn("says nothing about its rate", files(d)["text-thermochemie.tex"])

    def test_thermo_missing_data(self):
        r = AN.equation_result("Fe + O2 -> Fe2O3")
        self.assertIn("fehlen Bildungsdaten", r["thermo"]["error"])
        d = B.build({"state": {"equation": "Fe + O2 -> Fe2O3"}})
        self.assertIn("fehlen Bildungsdaten", files(d)["text-thermochemie.tex"])

    def test_nuclear(self):
        d = B.build({"state": {"equation": "^235U + n -> ^141Ba + ^92Kr + n"}})
        t = files(d)["text-gleichung.tex"]
        self.assertIn(r"3\,{}^{1}_{0}\mathrm{n}", t)
        self.assertIn(r"{}^{235}_{92}\mathrm{U}", t)


class Server(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = TemporaryDirectory()
        SV.STATE = SV.State(Path(cls.tmp.name))
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), SV.Handler)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.tmp.cleanup()

    def _post(self, path, body, origin=None):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json", **({"Origin": origin} if origin else {})})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_meta_and_run(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/api/meta") as r:
            m = json.loads(r.read())
        self.assertEqual(len(m["elements"]), 118)
        self.assertIn("ciaaw2021", m["refs"])
        code, out = self._post("/api/run", {"state": {"equation": "Fe + O2 -> Fe2O3"}})
        self.assertEqual(code, 200)
        self.assertEqual(out["equation"]["coefs"], ["4", "3", "2"])

    def test_constants_with_sources(self):                              # UI-13: Nachschlagefenster, Konstanten
        code, out = self._post("/api/constants", {})
        self.assertEqual(code, 200)
        by = {c["name"]: c for c in out["constants"]}
        self.assertEqual(by["NA"]["value"], 6.02214076e23)
        self.assertTrue(by["NA"]["exact"])
        for c in out["constants"]:
            self.assertTrue(c["source_short"], c["name"])                 # jede Konstante mit Quelle
            self.assertTrue(c["de"] and c["en"])

    def test_bundle_and_rebuild(self):
        code, d = self._post("/api/bundle", {"state": {"equation": "N2 + H2 <=> NH3"}, "lang": "de"})
        self.assertEqual(code, 200)
        self.assertIn(r"\rightleftharpoons", files(d)["text-gleichung.tex"])
        code, d2 = self._post("/api/bundle/rebuild", {"source": d["source"], "lang": "en"})
        self.assertEqual(code, 200)

    def test_foreign_origin_and_errors(self):
        code, _ = self._post("/api/run", {"state": {}}, origin="https://evil.example")
        self.assertEqual(code, 403)
        code, out = self._post("/api/species", {"formula": "Qq2"})
        self.assertEqual(code, 400)

    def test_search_substance_lookup(self):
        code, out = self._post("/api/search", {"q": "essig"})
        self.assertEqual(out["hits"][0]["formula"], "C2H4O2")
        code, out = self._post("/api/substance", {"q": "64-19-7"})
        self.assertEqual(code, 200)
        self.assertEqual(out["props"]["props"]["bp"][0]["v"], 118.0)
        self.assertTrue(out["pka"])
        code, out = self._post("/api/lookup", {"kind": "pka", "q": "Essigsäure"})
        self.assertAlmostEqual(out["choice"]["1"]["value"], 4.757)
        code, out = self._post("/api/lookup", {"kind": "ksp", "q": "AgCl"})
        self.assertAlmostEqual(out["choice"]["value"], -9.75)
        code, out = self._post("/api/substance", {"q": "Unbekanntium"})
        self.assertEqual(code, 404)

    def test_equation_species_in_collection(self):
        code, out = self._post("/api/run", {"state": {"equation": "Essigsäure + NaOH -> C2H3NaO2 + H2O"}})
        cards = out["equation"]["cards"]
        self.assertEqual(cards[0]["matches"][0]["de"], "Essigsäure")
        self.assertEqual(cards[2]["matches"], [])          # Natriumacetat ist nicht in der Test-Sammlung

    def test_own_substances(self):
        item = {"name": "Testharz", "formula": "C10H12O2", "kind": "polymer", "classes": ["Harze"],
                "values": {"density": [{"v": "1,2", "u": "g/cm³"}, {"v": 1.21, "u": "g/cm³", "T": 20}]},
                "source": {"type": "datasheet", "title": "Datenblatt Testharz", "container": "Hersteller", "year": "2026"}}
        code, out = self._post("/api/own/save", {"item": item})
        self.assertEqual(code, 200)
        key = out["key"]
        self.assertEqual(len(out["item"]["values"]["density"]), 1)        # "1,2" ist keine Zahl -> verworfen
        code, out = self._post("/api/search", {"q": "testharz"})
        self.assertEqual(out["hits"][0]["key"], key)
        code, out = self._post("/api/lookup", {"kind": "props", "q": "Testharz"})
        self.assertEqual(out["props"]["density"][0]["v"], 1.21)
        code, out = self._post("/api/run", {"state": {"equation": "Testharz + O2 -> CO2 + H2O"}})
        self.assertEqual(out["equation"]["coefs"], ["1", "12", "10", "6"])
        code, exp = self._post("/api/own/export", {})
        self.assertEqual(exp["format"], "folio-stoffe/1")
        code, out = self._post("/api/own/save", {"item": {"name": "", "formula": "C"}})
        self.assertEqual(code, 400)
        code, out = self._post("/api/own/save", {"item": {"name": "Kaputt", "formula": "Qq3"}})
        self.assertEqual(code, 400)
        code, out = self._post("/api/own/delete", {"id": key[4:]})
        self.assertTrue(out["deleted"])
        code, out = self._post("/api/own/import", {"data": exp})
        self.assertEqual(out["imported"], 1)

    def test_own_thermo_values(self):
        """Eigene Bildungsdaten mit Phase und Quelle gehen der Tabelle vor; ΔfG° wird aus ΔfH° und S° berechnet."""
        item = {"name": "Testwasserstoffperoxid", "formula": "H2O2",
                "values": {"dfH": [{"v": -187.78, "phase": "l"}], "S0": [{"v": 109.6, "phase": "l"}]},
                "source": {"type": "book", "title": "Testtabelle", "container": "Verlag", "year": "2026"}}
        code, out = self._post("/api/own/save", {"item": item})
        self.assertEqual(code, 200)
        self.assertEqual(out["item"]["values"]["dfH"][0]["phase"], "l")
        try:
            code, out = self._post("/api/run", {"state": {"equation": "H2O2 -> H2O + O2"}})
            th = out["equation"]["thermo"]
            self.assertEqual(th["rows"][0]["src"], "own")
            self.assertTrue(th["rows"][0]["Gcalc"])
            # ΔfG°(H2O2, l) = −187,78 − 298,15·(109,6 − 2·65,34 − 2·102,576)/1000 = −120,33 kJ/mol
            self.assertAlmostEqual(th["rows"][0]["G"], -120.33, delta=0.01)
            self.assertAlmostEqual(th["dH"], 2 * -285.83 + 2 * 187.78, delta=0.01)
        finally:
            for it in SV.STATE.own.items():
                self._post("/api/own/delete", {"id": it["id"]})


class Substances(unittest.TestCase):
    def test_resolve_and_names(self):
        from labcalc import substances as S
        self.assertEqual(S.resolve("Essigsäure"), "QTBSBXVTEAMEQO-UHFFFAOYSA-N")
        self.assertEqual(S.resolve("ETHANOIC ACID"), "QTBSBXVTEAMEQO-UHFFFAOYSA-N")
        self.assertEqual(S.resolve("AgCl"), "HKZLPVFGJNLROG-UHFFFAOYSA-M")
        self.assertIsNone(S.resolve("Essig"))                       # nur exakte Namen
        sp = C.parse_species("Silberchlorid")
        self.assertEqual(sp.unicode(), "AgCl")

    def test_choice_rule(self):
        from labcalc import substances as S
        v = S.pka("Essigsäure")
        self.assertEqual((v["source"], v["I"]), ("srd46", 0.0))      # I = 0 und kritisch ausgewählt zuerst
        self.assertEqual(len(S.pka_values("CH3COOH")["values"]), 3)
        self.assertAlmostEqual(S.pkb("Essigsäure")["value"], 13.995 - 4.757)
        self.assertAlmostEqual(S.logk("Ag+", "Cl-")["value"], 3.31)
        with self.assertRaises(C.ChemError):
            S.ksp("NaCl")

    def test_calc_functions(self):
        from labcalc import expr as E
        ctx = E.Context() if hasattr(E, "Context") else None
        f = E.STRFUNCS
        self.assertAlmostEqual(f["pKa"][0](ctx, "CH3COOH"), 4.757)
        self.assertAlmostEqual(f["Ksp"][0](ctx, "AgCl"), 10 ** -9.75)
        self.assertAlmostEqual(f["Tb"][0](ctx, "Essigsäure"), 391.15)
        self.assertAlmostEqual(f["rho"][0](ctx, "acetic acid"), 1049.0)

    def test_polymer_without_formula(self):
        from labcalc import substances as S
        m = S.get("poly:pe")
        self.assertIsNone(m["formula"])
        self.assertAlmostEqual(m["M_repeat_unit"], 2 * 12.011 + 4 * 1.008, places=4)


if __name__ == "__main__":
    unittest.main()
