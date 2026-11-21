"""Werkstoffdatenbank (labcalc.materials): Prüfung der Datei, Suche, Einheiten, Quellen, Rechner-Funktionen."""
import ast
import math
import unittest

from labcalc import expr as E
from labcalc import materials as M
from labcalc import units as U


class Database(unittest.TestCase):
    def test_file_is_valid(self):
        self.assertEqual(M.validate(), [])

    def test_classes_present(self):
        have = {r["klasse"] for r in M.materials()}
        for k in ("metall", "polymer", "keramik", "glas", "verbund", "faser"):
            self.assertIn(k, have)

    def test_zugversuch_rows_keep_their_fields(self):
        rows = M.zugversuch_rows()
        self.assertEqual(len(rows), 88)
        self.assertEqual(rows[0]["name"], "EN AW-1050A, weich")
        self.assertEqual(rows[-1]["name"], "GFK Gewebe")
        for r in rows:
            for f in ("name", "kategorie", "Rm_MPa", "A_pct", "E_GPa", "quelle"):
                self.assertIn(f, r)

    def test_every_value_has_a_source(self):
        for r in M.materials():
            for p in M.props_of(r):
                v = M.value(r, p)
                self.assertTrue(v["key"] or v["source"].get("title"), f"{r['id']}.{p}")


class Lookup(unittest.TestCase):
    def test_names_aliases_and_spelling(self):
        self.assertEqual(M.find("AISI 304")["id"], M.find("1.4301")["id"])
        self.assertEqual(M.find("en aw 6061 t6")["name"], "EN AW-6061-T6")
        self.assertEqual(M.find("Cu")["id"], "cu-rein")
        self.assertEqual(M.find("Alumina")["id"], "al2o3-999")

    def test_ambiguous_and_unknown(self):
        with self.assertRaisesRegex(M.MatError, "mehrdeutig"):
            M.find("C45")
        with self.assertRaisesRegex(M.MatError, "nicht in der Werkstoffdatenbank"):
            M.find("Unobtainium")
        with self.assertRaisesRegex(M.MatError, "kein Wert"):
            M.value("S235JR", "Eg")

    def test_si_conversion(self):
        self.assertAlmostEqual(M.get("Cu", "E"), 130e9)
        self.assertAlmostEqual(M.get("PE-HD", "Tg"), -90 + 273.15)          # °C in der Datei -> K
        self.assertAlmostEqual(M.get("1.4301", "alpha"), 17.2e-6)
        self.assertAlmostEqual(M.get("Al2O3", "KIc"), 5.05e6)                 # Mitte 4,2 … 5,9 MPa·√m
        self.assertAlmostEqual(M.get("Si", "Eg") / U.to_si(1, "eV"), 1.12)
        self.assertAlmostEqual(M.get("Ti", "c"), 0.46855e-9)
        self.assertEqual(M.text("Fe"), "krz")

    def test_zugversuch_fields_as_properties(self):
        v = M.value("1.4301", "Rm")
        self.assertAlmostEqual(v["si"], 645e6)
        self.assertEqual((v["min_si"], v["max_si"]), (540e6, 750e6))
        self.assertEqual(v["art"], "mitte")
        self.assertEqual(v["source"]["title"], "EN 10088-2, Kaltband C")
        self.assertIsNone(v["key"])
        self.assertAlmostEqual(M.get("S235JR", "Rp"), 235e6)
        self.assertAlmostEqual(M.get("S235JR", "A"), 0.26)

    def test_element_values_from_periodic_table(self):
        v = M.value("Cu", "Tm")
        self.assertEqual(v["key"], "pubchem_pt")
        self.assertAlmostEqual(v["si"], 1357.77, places=2)
        self.assertGreater(M.get("W", "rho"), 19000)

    def test_unchecked_values_are_marked(self):
        self.assertTrue(M.value("Cu", "E")["nicht_geprueft"])
        self.assertTrue(M.value("1.4301", "alpha")["nicht_geprueft"])

    def test_search_and_card(self):
        names = [s["name"] for s in M.search("glas", klasse="glas")]
        self.assertIn("Kalk-Natron-Glas", names)
        self.assertTrue(all(s["klasse"] == "polymer" for s in M.search(klasse="polymer")))
        self.assertTrue(all("Tg" in s["props"] for s in M.search(prop="Tg")))
        c = M.card("Cu")
        e = next(w for w in c["werte"] if w["prop"] == "E")
        self.assertEqual(e["text"], "130 GPa")
        self.assertEqual(e["key"], "crc97")


class Diffusion(unittest.TestCase):
    def test_carbon_in_austenite(self):
        # D = 2,3·10⁻⁵ m²/s · exp(−148 kJ/mol / (R · 1273,15 K))
        d = M.D_diff("C", "γ-Fe", 1273.15)
        self.assertAlmostEqual(d, 2.3e-5 * math.exp(-148000 / (8.31446261815324 * 1273.15)), delta=1e-20)
        self.assertEqual(M.D_diff("C", "gamma-Fe", 1273.15), d)
        with self.assertRaises(M.MatError):
            M.diffusion("Au", "Ag")


class CalcFunctions(unittest.TestCase):
    def ev(self, s):
        ctx = E.Ctx()
        return E.evaluate(E.parse(s, ctx.callables()), ctx)

    def test_values_and_units(self):
        self.assertAlmostEqual(self.ev('mat("Cu", "E")'), 130e9)
        self.assertAlmostEqual(self.ev('E_mat("Cu") / G_mat("Cu")'), 130 / 48)
        node = ast.parse('mat("Cu", "E")', mode="eval").body
        self.assertTrue(U.deq(E.strfunc_dims(node), U.kind_dims("modulus")))
        node = ast.parse('mat("Cu", "Tm")', mode="eval").body
        self.assertTrue(U.deq(E.strfunc_dims(node), U.kind_dims("temperature")))
        node = ast.parse('mat("Cu", "x")', mode="eval").body
        self.assertIsNone(E.strfunc_dims(node))

    def test_function_overview_group(self):
        group = dict(E.FUNC_DOC).get("Werkstoffe")
        self.assertTrue(group and any(s.startswith("mat(") for s in group))

    def test_sources_of_a_line(self):
        recs = M.cite_records('x = E_mat("Cu") + mat("1.4301", "Rm") + D_diff("C", "γ-Fe", T)')
        self.assertEqual([r["key"] for r in recs], ["crc97", None, "callister"])
        self.assertEqual(recs[1]["source"]["title"], "EN 10088-2, Kaltband C")


class Ranges(unittest.TestCase):
    """data/ranges.json: cited min–max ranges per material and property (areas in the Ashby chart)."""
    MAIN = ("rho", "E", "Rp", "Rm", "A", "sigma_f", "sigma_c", "KIc", "HV", "Tm", "Tg", "alpha", "lambda", "cp", "rho_el")

    @classmethod
    def setUpClass(cls):
        M.reload()
        cls.data = M._ranges()
        cls.bereiche = cls.data.get("bereiche") or {}

    def test_file_header(self):
        self.assertEqual(self.data.get("_format"), "folio-ranges/1")
        meta = M.ranges_meta()
        self.assertTrue(meta["de"] and meta["en"])
        ids = {r["id"] for r in M.materials()}
        self.assertEqual(set(self.bereiche) - ids, set(), "ranges for unknown material ids")

    def test_every_material_has_rho_and_E_and_its_main_props(self):
        for r in M.materials():
            have = M.props_of(r)
            mine = self.bereiche.get(r["id"]) or {}
            for p in ("rho", "E"):
                if p in have:
                    self.assertIn(p, mine, f"{r['id']}.{p}")
            for p in self.MAIN:
                if p in have:
                    self.assertIn(p, mine, f"{r['id']}.{p}")
            self.assertTrue({"rho", "E"} <= set(mine), f"{r['id']}: rho and E range for the default Ashby axes")

    def test_ranges_are_ordered_convertible_and_cited(self):
        from labcalc import sources as S
        quellen = self.data.get("quellen") or {}
        for k, rec in quellen.items():
            self.assertNotIn(k, S.REFS, f"source key {k} shadows a labcalc key")
            self.assertTrue(rec.get("title") and rec.get("type"), k)
            self.assertIn("nicht am Original geprüft", rec.get("note", ""), k)
            self.assertNotIn("doi", rec, k)
        for mid, props in self.bereiche.items():
            for p, b in props.items():
                where = f"{mid}.{p}"
                self.assertIn(p, M.PROPS, where)
                self.assertLess(b["min"], b["max"], where)
                self.assertTrue(b["q"] in quellen or b["q"] in S.REFS, f"{where}: source {b['q']} unknown")
                self.assertIn(b.get("art"), ("norm", "datenblatt", "handbuch", "literatur"), where)
                self.assertEqual(b["u"], M.PROPS[p][1], f"{where}: unit should be the display unit")
                _, dims, _ = U.parse_unit(b["u"])
                if M.PROPS[p][0] != "number":
                    self.assertTrue(U.deq(dims, U.kind_dims(M.PROPS[p][0])), where)
                rg = M.range_of(mid, p)
                self.assertLess(rg["min_si"], rg["max_si"], where)
                self.assertTrue(rg["range_source"].get("title"), where)

    def test_stored_values_lie_inside_their_range(self):
        for mid, props in self.bereiche.items():
            have = M.props_of(mid)
            for p, b in props.items():
                if p not in have:
                    continue
                v = M.value(mid, p)
                rg = M.range_of(mid, p)
                inside = rg["min_si"] * (1 - 1e-9) <= v["si"] <= rg["max_si"] * (1 + 1e-9)
                self.assertTrue(inside or b.get("note"), f"{mid}.{p}: stored value outside range without note")

    def test_value_takes_range_from_file_when_it_has_none(self):
        v = M.value("S235JR", "Rp")                        # stored 235 MPa, no own range
        self.assertAlmostEqual(v["si"], 235e6)
        self.assertEqual((v["min_si"], v["max_si"]), (235e6, 355e6))
        self.assertEqual(v["range_key"], "en10025_2")
        self.assertIn("EN 10025-2", v["range_source"]["title"])
        self.assertEqual(v["range_art"], "norm")
        self.assertFalse(v["range_own"])
        self.assertIsNone(v["key"])                         # the value keeps its own source
        v = M.value("Cu", "E")
        self.assertEqual(v["range_source"]["title"], "ASM Handbook, Vol. 2: Properties and Selection: Nonferrous "
                                                     "Alloys and Special-Purpose Materials")
        v = M.value("PE-HD", "Tg")                          # °C range -> K
        self.assertAlmostEqual(v["min_si"], -125 + 273.15)
        self.assertEqual(v["range_key"], "mark2007")
        self.assertEqual(v["range_source"]["authors"], "Mark, J. E.")

    def test_own_range_wins_and_cites_the_value(self):
        v = M.value("1.4301", "Rm")
        self.assertEqual((v["min_si"], v["max_si"]), (540e6, 750e6))
        self.assertTrue(v["range_own"])
        self.assertEqual(v["range_source"], v["source"])
        v = M.value("Al2O3", "KIc")
        self.assertEqual(v["range_key"], "callister")

    def test_card_text_unchanged_by_file_ranges(self):
        e = next(w for w in M.card("Cu")["werte"] if w["prop"] == "E")
        self.assertEqual(e["text"], "130 GPa")

    def test_missing_file_means_no_ranges(self):
        import tempfile
        from pathlib import Path
        old = M.DATA
        with tempfile.TemporaryDirectory() as td:
            M.DATA = Path(td)
            M._ranges.cache_clear()
            try:
                self.assertEqual(M._ranges(), {})
                self.assertIsNone(M.range_of("S235JR", "Rp"))
                v = M.value("S235JR", "Rp")
                self.assertIsNone(v["min_si"])
                self.assertIsNone(v["range_key"])
            finally:
                M.DATA = old
                M._ranges.cache_clear()


# fixed sample in the shape of the Materials Project /materials/summary/ answer ("data"); no download in tests
MP_SAMPLE = {
    "Fe": [{"material_id": "mp-13", "formula_pretty": "Fe", "density": 8.0, "band_gap": 0.0,
            "bulk_modulus": {"voigt": 190.0, "reuss": 180.0, "vrh": 185.0},
            "shear_modulus": {"voigt": 95.0, "reuss": 85.0, "vrh": 90.0},
            "symmetry": {"crystal_system": "Cubic", "symbol": "Im-3m"}, "energy_above_hull": 0.0,
            "is_stable": True, "theoretical": False}],
    "Si": [{"material_id": "mp-149", "formula_pretty": "Si", "density": 2.3, "band_gap": 0.6,
            "bulk_modulus": None, "shear_modulus": None, "symmetry": {"crystal_system": "Cubic", "symbol": "Fd-3m"},
            "energy_above_hull": 0.0, "is_stable": True, "theoretical": False}],
    "C": [],
}


class OptionalMaterialsProject(unittest.TestCase):
    def test_rows_from_sample(self):
        rows = {r["id"]: r for r in M.mp_rows(MP_SAMPLE, "2026-11-18")}
        self.assertEqual(set(rows), {"mp-13", "mp-149"})
        fe = rows["mp-13"]
        self.assertEqual(fe["klasse"], "metall")
        self.assertNotIn("Eg", fe["werte"])                       # metals: no band gap entry
        self.assertEqual(fe["werte"]["K"], {"v": 185.0, "u": "GPa", "q": "dejong2015"})
        self.assertAlmostEqual(fe["werte"]["E"]["v"], 9 * 185 * 90 / (3 * 185 + 90), places=1)
        self.assertAlmostEqual(fe["werte"]["nu"]["v"], (3 * 185 - 2 * 90) / (2 * (3 * 185 + 90)), places=3)
        self.assertEqual(fe["werte"]["struktur"]["v"], "Im-3m Cubic")
        self.assertIn("2026-11-18", fe["hinweis"])
        si = rows["mp-149"]
        self.assertEqual((si["klasse"], si["werte"]["Eg"]["v"]), ("halbleiter", 0.6))
        self.assertNotIn("K", si["werte"])

    def test_optional_file_is_merged_and_cited(self):
        import json
        import shutil
        import tempfile
        from pathlib import Path
        old_data, old_path = M.DATA, M.PATH
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            shutil.copyfile(old_path, d / "materials.json")
            (d / "optional").mkdir()
            (d / "optional" / "materials_mp.json").write_text(
                json.dumps({"werkstoffe": M.mp_rows(MP_SAMPLE, "2026-11-18")}), encoding="utf-8")
            M.DATA, M.PATH = d, d / "materials.json"
            M.reload()
            try:
                self.assertAlmostEqual(M.get("mp-13", "K"), 185e9)
                self.assertEqual(M.find("Fe (computed, mp-13)")["id"], "mp-13")
                v = M.value("mp-149", "Eg")
                self.assertEqual(v["key"], "jain2013")
                self.assertTrue(v["nicht_geprueft"])                # DFT values are flagged in every card and value
                self.assertIn("DFT", M.card("mp-13", "en")["nicht_geprueft"])
                self.assertEqual(M.find("Fe-rein")["id"], "fe-rein")  # curated entries keep their names
            finally:
                M.DATA, M.PATH = old_data, old_path
                M.reload()


if __name__ == "__main__":
    unittest.main()
