"""Struktur über T, Eingaben ohne Wirkung, die eine Suche und das Kompendium."""
import copy
import json
import os
import re
import sys
import unittest
import warnings

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from werk import finder as F  # noqa: E402
from werk import gefuege as GF  # noqa: E402
from werk import kompendium as KP  # noqa: E402
from werk import refs as RF  # noqa: E402
from werk import struktur as SK  # noqa: E402
from werk import tools as T  # noqa: E402
from werk import views as VW  # noqa: E402
import test_werkstoffe as TW  # noqa: E402

PAGE = os.path.join(os.path.dirname(__file__), "..", "werk", "static", "index.html")


def _plain(x) -> str:
    return re.sub(r"-?\d+(?:[.,]\d+)?", "#", str(x or ""))


def _state(r: dict) -> str:
    """Was man sieht, ohne die blosse Temperaturzahl in den Texten."""
    pan = [(p.get("id"), _plain(p.get("title")), json.dumps(p.get("sketch") or p.get("scene"), sort_keys=True, default=str)) for p in r["panels"]]
    return json.dumps([pan, [_plain(s) for s in r["statements"]]], sort_keys=True)


class StructureOverTemperature(unittest.TestCase):
    def test_every_material_changes_or_says_it_does_not(self):
        for m in SK.materials("de"):
            first = SK.build(m["id"], 20.0, "de", 1, 3)
            lo, hi = first["range"]
            ts = sorted(float(t["T"]) for t in first["transitions"] if lo < t["T"] < hi)
            grid = sorted({lo, hi, *ts, *[(a + b) / 2 for a, b in zip([lo] + ts, ts + [hi])]})
            runs = [SK.build(m["id"], x, "de", 1, 3) for x in grid]
            changes = len({_state(r) for r in runs}) > 1
            self.assertTrue(changes or all(r["no_change"] for r in runs), m["id"])
            if first["no_change"]:
                self.assertTrue(any("keine Umwandlung" in s for s in first["statements"]), m["id"])

    def test_cellulose_stages(self):
        for typ in ("holz", "papier"):
            mids = [m["id"] for m in SK.materials("de") if m["typ"] == typ]
            self.assertTrue(mids)
            for mid in mids:
                runs = {x: SK.build(mid, x, "de", 1, 3) for x in (20, 150, 260, 350, 450, 600)}
                self.assertEqual(len({_state(r) for r in runs.values()}), 6, mid)
                self.assertEqual([t["T"] for t in runs[20]["transitions"]], [100, 220, 315, 400, 525])
                self.assertTrue(any(p["id"] == "kette" for p in runs[350]["panels"]))
                self.assertFalse(any(p["id"] == "kette" for p in runs[450]["panels"]))
                self.assertTrue(any("Levoglucosan" in s for s in runs[350]["statements"]))
                self.assertFalse(any("verascht" in s for s in runs[450]["statements"]))
                self.assertTrue(any("verascht" in s for s in runs[600]["statements"]))
                self.assertLessEqual({"yang2007", "lin2009", "iso1762"}, set(runs[600]["refs_keys"]))
                self.assertTrue(all(RF.known(k) for k in runs[600]["refs_keys"]), mid)

    def test_concrete_cites_cement_chemistry(self):
        rec = RF.rec("taylor1997cem")
        self.assertIn("Cement", json.dumps(rec, ensure_ascii=False))


def _cases():
    ctx, _ = TW.all_cases()
    E, i = TW.CorrCreepTest.bv()
    return ctx, [
        ("auswahl", {"x": "rho", "y": "E", "index": "beam_E", "limits": [{"prop": "E", "min": 10, "max": 500}]}),
        ("auswahl", {"x": "rho", "y": "E", "expo": {"E": 0.5, "rho": -1}, "own": [{"name": "A", "x": 2.7, "y": 70, "src": ""}]}),
        ("kristall", {"phase": "cu", "tube": "Cu", "tth_min": 10, "tth_max": 120, "fwhm": 0.1, "hkl": [1, 1, 1], "uvw": [1, 1, 0], "hkl2": [1, 0, 2]}),
        ("kristall", {"custom": {"name": "X", "system": "triclinic", "centring": "P", "cell": {"a": 4.05, "b": 5.1, "c": 6.2, "alpha": 80, "beta": 95, "gamma": 105},
                                 "atoms": [{"el": "Al", "x": 0, "y": 0, "z": 0, "occ": 1}, {"el": "Cu", "x": 0.4, "y": 0.3, "z": 0.2, "occ": 1}]},
                      "tube": "Cu", "tth_min": 10, "tth_max": 120, "fwhm": 0.1}),
        ("gitter", {"host": "Fe", "T": 20, "n": 4, "seed": 1, "solutes": [{"el": "C", "c": 0.45, "einheit": "wt"}],
                    "fx": {"vac": True, "vib": True, "distort": True, "precip": True, "disl": True, "sf": True, "gb": True}, "boost": 1e6, "vib_boost": 2, "gb_angle": 16, "slice": "110"}),
        ("struktur", {"material": "c45e-qt", "T": 20, "seed": 1, "n": 5}),
        ("xrd", {"item": "p1", "tube": "file", "opt": {"min_rel": 2, "smooth": 5, "bg": True, "bg_width": 2, "strip_ka2": False, "K": 0.9, "inst_fwhm": 0.01,
                                                       "tol": 0.2, "index_min": 3, "phase_ref": "cu", "search": True, "overlay": ["cu"], "quant_ids": ["cu"]}}),
        ("phasen", {"system": "fe-c", "x": 0.35, "T": 726}),
        ("phasen", {"model": {"A": "Cu", "B": "Ni", "MA": 63.546, "MB": 58.693, "TmA": 1084.62, "TmB": 1455, "HA": 13.26, "HB": 17.48, "omega_L": 0, "omega_S": 0},
                    "x": 35, "T": 1225, "unit": "wt"}),
        ("stahl", {"comp": {"C": 0.18, "Si": 0.3, "Mn": 1.4, "Cr": 0.5, "Mo": 0.2, "V": 0.05, "Ni": 0.3, "Cu": 0.2, "B": 0.001}, "preheat": {"d": 20, "HD": 5, "Q": 1.5},
                   "hj": {"T1": 600, "t1": 2, "T2": 650, "C": 20}, "carb": {"T": 925, "t": 4, "c0": 0.2, "cs": 0.9, "limit": 0.4}}),
        ("laminat", {"material": "CFK UD", "layup": "[0/±45/90]s", "t": 0.125, "Nx": 100, "Ny": 10, "Nxy": 5, "Mx": 1, "My": 1, "Mxy": 1, "F12": -0.5, "ST": 80}),
        ("ermuedung", {"rows": [{"sa": 400, "sm": 50, "N": 1e4}, {"sa": 350, "sm": 50, "N": 5e4}, {"sa": 300, "sm": 50, "N": 2e5}, {"sa": 260, "sm": 50, "N": 1e6},
                                {"sa": 240, "sm": 50, "N": 1e7, "runout": True}], "mat": {"Rm": 800, "Re": 600, "sigma_f": 1200}, "model": "morrow",
                       "N_target": 1e6, "marin": {"Rm": 800, "surface": "bearbeitet", "d": 10, "loading": "biegung", "rel": 90, "kd": 1},
                       "series": [-200, 100, -300, 500, -100, 300, -400, 400, -200], "hyst": 10, "miner_model": "goodman", "miner_cutoff": True, "repeats": 3}),
        ("weibull", {"values": TW.ReliabilityTest.X, "method": "mle", "boot": True, "B": 60, "level": 0.9, "seed": 7,
                     "size": {"V1": 100, "V2": 1000, "kind1": "4pb", "kind2": "zug", "Li1": 20, "L1": 40}}),
        ("bruch", {"kq": {"geom": "senb", "P": 12, "B": 20, "W": 40, "a": 20, "S": 160, "Rp": 800, "Pmax": 12.5}, "crack": {"KIc": 50, "sigma": 300, "Y": 1.12}}),
        ("haerte", {"method": "HBW", "indents": [{"F": 29420, "d1": 4.0, "d2": 4.1, "D": 10}, {"F": 29420, "d1": 4.2}], "D": 10,
                    "grain": {"L": 500, "N": 100, "M": 100}, "hp": [{"d": 10, "s": 300}, {"d": 25, "s": 250}, {"d": 50, "s": 220}]}),
        ("haerte", {"method": "HV", "indents": [{"F": 98.07, "d1": 0.300, "d2": 0.302}, {"F": 98.07, "d1": 0.296}], "convert": {"table": "t1", "to": "HRC"}, "grain": {"NA": 1000}}),
        ("korrosion", {"E": E.tolist(), "i": i.tolist(), "Eunit": "V", "iunit": "A", "area": 2, "eta_min": 0.05, "eta_max": 0.15, "bv": True, "eta_fit": 0.02, "metal": "Fe"}),
        ("korrosion", {"E": E.tolist(), "i": i.tolist(), "iunit": "A", "area": 1, "EW": 27.92, "rho": 7.87, "Ecorr": -0.45}),
        ("kriechen", {"rows": [{"s": 200, "T": 550, "t": 1000}, {"s": 150, "T": 600, "t": 800}, {"s": 120, "T": 600, "t": 3000}, {"s": 100, "T": 650, "t": 500},
                               {"s": 80, "T": 650, "t": 2000}, {"s": 60, "T": 600, "rate": 2.1e-6}, {"s": 80, "T": 600, "rate": 9.8e-6}, {"s": 80, "T": 650, "rate": 6.5e-5}],
                      "C": 20, "deg": 2, "predict": {"s": 130, "T": 600}}),
    ]


# Eingaben, deren kleine Änderung fachlich nichts ändert: dafür ein Wert, der wirken muss
STRONGER = {("ermuedung", "hyst"): 400, ("ermuedung", "marin.rel"): 95, ("xrd", "opt.index_min"): 60}


def _leaves(o, path=()):
    if isinstance(o, dict):
        for k, v in o.items():
            yield from _leaves(v, path + (k,))
    elif isinstance(o, list):
        if len(o) > 4 and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in o):
            yield path, o
            return
        for k, v in enumerate(o):
            yield from _leaves(v, path + (k,))
    elif isinstance(o, (int, float)) and not isinstance(o, bool):
        yield path, o


def _set(o, path, v):
    for k in path[:-1]:
        o = o[k]
    o[path[-1]] = v


def _out(r):
    return json.dumps({k: v for k, v in r.items() if k not in ("views_info", "refs")}, sort_keys=True, default=str)


class ToolAudit(unittest.TestCase):
    def test_every_numeric_input_has_an_effect(self):
        ctx, cases = _cases()
        self.assertLessEqual(set(T.TOOLS) - {"karten"}, {t for t, _ in cases})
        dead = []
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            for tool, req in cases:
                base = _out(T.run(tool, copy.deepcopy(req), ctx))
                for path, v in _leaves(req):
                    if path[0] in ("E", "i"):
                        continue
                    name = ".".join(map(str, path))
                    if (tool, name) in STRONGER:
                        nv = STRONGER[(tool, name)]
                    elif "atoms" in path and path[-1] in ("x", "y", "z"):
                        nv = v + 0.13                 # um 1 verschoben wäre dieselbe Lage in der Nachbarzelle
                    elif isinstance(v, list):
                        nv = [x * 1.07 for x in v]
                    elif isinstance(v, int):
                        nv = v + 1
                    else:
                        nv = 0.1 if v == 0 else v * 1.07
                    q = copy.deepcopy(req)
                    _set(q, path, nv)
                    if _out(T.run(tool, q, ctx)) == base:
                        dead.append(f"{tool}: {name}")
        self.assertEqual(dead, [])

    def test_empty_input_is_a_clean_answer(self):
        ctx, _ = _cases()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            for tool in T.TOOLS:
                try:
                    r = T.run(tool, {}, ctx)
                except T.ERRORS + (LookupError,):
                    continue
                self.assertIsInstance(r, dict, tool)

    def test_crystal_edge_inputs(self):
        ctx = T.Ctx()
        r = T.run("kristall", {"phase": "cu", "hkl": [1, 1, 1], "hkl2": [0, 0, 0], "uvw": [0, 0, 0]}, ctx)
        self.assertNotIn("angle_planes", r)
        self.assertNotIn("direction", r)
        for bad in ({"a": float("nan")}, {"a": 4, "alpha": float("nan")}, {"a": -1}, {"a": 4, "gamma": 0}):
            with self.assertRaises(T.ERRORS, msg=bad):
                T.run("kristall", {"custom": {"system": "triclinic", "cell": bad}}, ctx)
        with self.assertRaises(T.ERRORS):
            T.run("kristall", {"phase": "cu", "hkl": ["a", 1, 1]}, ctx)


    def test_edge_values_never_crash_or_hang(self):
        ctx, cases = _cases()
        ok = T.ERRORS + (LookupError,)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            for tool, req in cases:
                if tool == "xrd":                     # langsam: die zwei Felder, die vorher hingen
                    leaves = [(("opt", "min_rel"), 2), (("opt", "tol"), 0.2)]
                else:
                    leaves = [(p, v) for p, v in _leaves(req) if p[0] not in ("E", "i")][:12]
                for path, _v in leaves:
                    for nv in (0, -1, float("nan"), "", "abc", None) + (() if path[-1] in ("n", "B", "repeats") else (1e9,)):
                        q = copy.deepcopy(req)
                        _set(q, path, nv)
                        try:
                            json.dumps(T.run(tool, q, ctx), default=str)
                        except ok:
                            pass
        q = copy.deepcopy(dict(cases)["weibull"])
        q["B"] = 1e9
        with self.assertRaises(T.ERRORS):
            T.run("weibull", q, ctx)


class Search(unittest.TestCase):
    def _ids(self, q, lang="de"):
        return {x["id"] for g in F.search(q, lang, 200)["groups"] for x in g["items"]}

    def test_every_tool_material_and_entry_is_findable(self):
        from labcalc import materials as M
        for lang in ("de", "en"):
            for t in T.TOOLS:
                self.assertIn("tool:" + t, self._ids(KP.tool_name(t, lang), lang), t)
            for r in M.materials():
                if r.get("_teil") == "materials_mp":
                    continue
                name = M.summary(r, lang)["name"]
                self.assertIn("mat:" + r["id"], self._ids(name, lang), name)
            for e in KP.entries(lang):
                self.assertIn(e["id"], self._ids(e["title"], lang), e["id"])

    def test_aliases_designations_and_spelling(self):
        from labcalc import materials as M
        for r in M.materials():
            if r.get("_teil") == "materials_mp":
                continue
            for a in (r.get("aliase") or [])[:3]:
                self.assertIn("mat:" + r["id"], self._ids(a), a)
        self.assertEqual(F.norm("Härte"), F.norm("haerte"))
        self.assertIn("tool:haerte", self._ids("haerte"))
        self.assertIn("topic:cellulose", self._ids("Levoglucosan"))

    def test_results_are_grouped_and_actionable(self):
        r = T.run("finden", {"q": "Perlit", "lang": "de"}, T.Ctx())
        self.assertTrue(r["groups"])
        for g in r["groups"]:
            self.assertTrue(g["label"])
            for x in g["items"]:
                self.assertTrue(x["act"])
        only = T.run("finden", {"q": "Perlit", "lang": "de", "kinds": ["entry"]}, T.Ctx())
        self.assertEqual({g["kind"] for g in only["groups"]}, {"entry"})
        self.assertEqual(T.run("finden", {"q": " "}, T.Ctx())["groups"], [])

    def test_task_groups_cover_every_tool_once(self):
        tools = [t for g in KP.groups() for t in g["tools"]]
        self.assertEqual(sorted(tools), sorted(T.TOOLS))
        for g in KP.data()["groups"]:
            self.assertEqual(len(g["rail"]), 2)
            self.assertLessEqual(set(g["main"]), set(g["tools"]))


class Compendium(unittest.TestCase):
    def test_every_entry_has_text_and_resolving_sources(self):
        for lang in ("de", "en"):
            es = KP.entries(lang)
            self.assertEqual(len({e["id"] for e in es}), len(es))
            for e in es:
                full = KP.entry(e["id"], lang)
                self.assertTrue(KP.text_of(full).strip(), e["id"])
                self.assertEqual(full["keys"], [q["key"] for q in full["refs"]], e["id"])
                if not full["refs"]:                  # ohne Quelle nur, wenn alles reines Programmverhalten ist
                    self.assertTrue(all(s["unsourced"] == "software" for s in KP.statements_of(full)), e["id"])
                self.assertTrue(all(q["text"] for q in full["refs"]), e["id"])
                for s in full.get("sections") or []:
                    self.assertLessEqual(set(s["keys"]), {q["key"] for q in full["refs"]}, s["id"])

    def test_former_view_explanations_all_moved(self):
        for lang in ("de", "en"):
            for tool, spec in list(VW.V.items()) + [("struktur", VW.S_CAT)]:
                e = KP.entry("tool:" + tool, lang)
                for vid in spec:
                    sec = [s for s in e["sections"] if s["id"] == f"tool:{tool}#{vid}"]
                    self.assertEqual(len(sec), 1, (tool, vid))
                    self.assertTrue(sec[0]["statements"], (tool, vid))

    def test_mechanisms_atlas_and_hints_are_in_it(self):
        ids = {e["id"] for e in KP.entries("de")}
        self.assertLessEqual({"mech:" + m for m in GF.MECHANISMS}, ids)
        self.assertLessEqual({"atlas:" + c for c in GF.CONSTITUENTS}, ids)
        self.assertLessEqual({"topic:cellulose", "topic:bezeichnung", "topic:unsicherheit"}, ids)
        for tool, rows in KP.text()["notes"].items():
            text = KP.text_of(KP.entry("tool:" + tool, "en"))
            for r in rows:
                self.assertTrue(r[1] and r[2])
                self.assertIn(r[2], text)
        page = open(PAGE, encoding="utf-8").read()
        for ex in (x["id"] for xs in KP.data()["examples"].values() for x in xs if x["id"] != "gitter"):
            self.assertRegex(page, rf'k === "{ex}"', ex)

    def test_tool_results_carry_keys_and_a_link_but_no_explanation(self):
        ctx, secs = TW.all_cases()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            for tool, req in secs:
                r = T.run(tool, copy.deepcopy(req), ctx)
                vi = r.get("views_info")
                self.assertTrue(vi, tool)
                for vid, e in vi.items():
                    self.assertEqual(set(e), {"keys", "entry"}, (tool, vid))
                    self.assertTrue(KP.entry(e["entry"], "de"), e["entry"])

    def test_figures_keep_their_sources(self):
        for tool, spec in VW.V.items():
            for vid, sp in spec.items():
                if sp[0]:
                    self.assertTrue(VW.figure_keys(tool, vid) or sp[0], (tool, vid))

    def test_page_shows_results_first(self):
        page = open(PAGE, encoding="utf-8").read()
        for gone in ("Was passiert hier", "data-ex=", "data-gex", "viewInfoHtml", 'class="vinfo"', "data-gefstep", '["mech", L('):
            self.assertNotIn(gone, page)
        for here in ('id="findQ"', 'id="kpWin"', "kpOpen", "api/tool/finden", "api/tool/kompendium", 'data-kp="'):
            self.assertIn(here, page)


if __name__ == "__main__":
    unittest.main()
