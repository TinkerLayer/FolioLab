"""Das Kompendium als Quelle: jede Aussage mit Kennung und Quelle oder ausdrücklich ohne, je Werkstoff ein Eintrag aus den
zitierten Daten, Prüfstatus ohne Beschönigung, und die Übernahme aus dem Projektindex mit Einheitenprüfung."""
import json
import os
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from labcalc import materials as M  # noqa: E402
from werk import finder as F  # noqa: E402
from werk import kompendium as KP  # noqa: E402
from werk import refs as RF  # noqa: E402
from werk import select as SL  # noqa: E402
from werk import tools as T  # noqa: E402
from werk import views as VW  # noqa: E402

PAGE = os.path.join(os.path.dirname(__file__), "..", "werk", "static", "index.html")
TEXT = os.path.join(os.path.dirname(__file__), "..", "werk", "data", "kompendium_text.json")
_CACHE: dict = {}


def full(lang: str) -> list[dict]:
    if lang not in _CACHE:
        _CACHE[lang] = [KP.entry(x["id"], lang) for x in KP.entries(lang)]
    return _CACHE[lang]


def stmts(lang: str):
    for e in full(lang):
        for s in KP.statements_of(e):
            yield e, s


class Statements(unittest.TestCase):
    def test_every_statement_has_id_text_and_keys_or_a_flag(self):
        for lang in ("de", "en"):
            seen = set()
            for e, s in stmts(lang):
                self.assertTrue(s["id"].startswith(e["id"]), s["id"])
                self.assertNotIn(s["id"], seen)
                seen.add(s["id"])
                self.assertTrue(s["text"].strip(), s["id"])
                if s["keys"]:
                    self.assertIsNone(s["unsourced"], s["id"])
                else:
                    self.assertIn(s["unsourced"], ("software", "open"), s["id"])
                    self.assertEqual(s["basis"], "none", s["id"])

    def test_every_cited_key_resolves_in_the_entry(self):
        for lang in ("de", "en"):
            for e in full(lang):
                have = {q["key"]: q for q in e["refs"]}
                self.assertTrue(all(q["text"].strip() for q in e["refs"]), e["id"])
                for s in KP.statements_of(e):
                    self.assertLessEqual(set(s["keys"]), set(have), s["id"])

    def test_raw_text_cites_only_known_sources(self):
        d = json.loads(Path(TEXT).read_text(encoding="utf-8"))
        rows = [r for v in d["sections"].values() for rs in v.values() for r in rs] + [r for rs in d["notes"].values() for r in rs] + [r for rs in d["topics"].values() for r in rs]
        self.assertTrue(rows)
        for r in rows:
            self.assertTrue(r[1].strip() and r[2].strip(), r[0])
            for k in r[3]:
                self.assertTrue(RF.known(k), (r[0], k))
            if len(r) > 4:
                self.assertIn(r[4], ("sw", "open"), r[0])

    def test_de_and_en_are_the_same_statements_with_the_same_citations(self):
        de = {s["id"]: s for _, s in stmts("de")}
        en = {s["id"]: s for _, s in stmts("en")}
        self.assertEqual(set(de), set(en))
        for sid, s in de.items():
            self.assertEqual(s["keys"], en[sid]["keys"], sid)
            self.assertEqual(s["unsourced"], en[sid]["unsourced"], sid)

    def test_bainite_is_not_cited_to_bain(self):
        for lang in ("de", "en"):
            for _e, s in stmts(lang):
                if re.search(r"[Bb]ainit", s["text"]) and not re.search(r"Bain(?!it)", s["text"]):
                    self.assertNotIn("bain1924", s["keys"] if s["basis"] == "statement" else [], s["id"])

    def test_nothing_claims_to_be_checked(self):
        allowed = {"unchecked", "partial", "no_record"}
        for e, s in stmts("de"):
            self.assertIn(s["check"], {"unchecked", "mixed", "partial", "no_record", "none"}, s["id"])
        for e in full("de"):
            for q in e["refs"]:
                self.assertIn(q["status"], allowed, q["key"])
                self.assertEqual(q["unchecked"], q["status"] == "unchecked", q["key"])

    def test_a_record_saying_unchecked_stays_unchecked(self):
        for e in full("de"):
            for q in e["refs"]:
                if RF.NG in q["text"]:
                    self.assertEqual(q["status"], "unchecked", q["key"])

    def test_no_teaching_tone(self):
        bad = re.compile(r"was passiert|stell dir|merke:|einfach gesagt|what happens here|imagine|in simple terms|keep in mind", re.I)
        for lang in ("de", "en"):
            for _e, s in stmts(lang):
                self.assertIsNone(bad.search(s["text"]), s["id"])

    def test_statement_lookup_round_trip(self):
        for sid in ("atlas:ferrit.1", "mech:bain.1.1", "tool:auswahl#_.index", "material:c45e-qt.E"):
            s = KP.statement(sid, "en")
            self.assertEqual(s["id"], sid)
            self.assertEqual([q["key"] for q in s["refs"]], s["keys"])
        with self.assertRaises(LookupError):
            KP.statement("material:c45e-qt.gibtesnicht", "de")
        r = T.run("kompendium", {"statement": "material:c45e-qt.E", "lang": "de"}, T.Ctx())
        self.assertEqual(r["statement"]["id"], "material:c45e-qt.E")

    def test_balance_adds_up(self):
        b = KP.balance("de")
        self.assertEqual(b["entries"], 195)
        self.assertEqual(b["statements"], b["cited"] + b["open"] + b["software"])
        self.assertEqual(b["sources"], b["sources_unchecked"] + b["sources_partial"] + b["sources_no_record"])


class MaterialEntries(unittest.TestCase):
    def test_every_material_has_an_entry(self):
        ids = {e["id"] for e in KP.entries("de")}
        mats = M.materials()
        self.assertEqual(len(mats), 136)
        self.assertLessEqual({"material:" + r["id"] for r in mats}, ids)
        self.assertEqual(len(ids), 195)

    def test_values_are_those_of_the_database_with_their_status(self):
        for r in M.materials():
            e = KP.entry("material:" + r["id"], "de")
            self.assertEqual(e["title"], M.summary(r, "de")["name"])
            vals = {s["prop"]: s for s in e["statements"] if "prop" in s}
            self.assertLessEqual(set(M.props_of(r)), set(vals), r["id"])
            for p, s in vals.items():
                try:
                    v = M.value(r, p)
                except M.MatError:                     # nur eine Spanne hinterlegt
                    self.assertIsNone(s["value"], (r["id"], p))
                    self.assertTrue(s["range_keys"], (r["id"], p))
                    self.assertEqual(s["range_status"], "unchecked", (r["id"], p))
                    continue
                if v.get("si") is None:
                    self.assertEqual(s["shown"], v.get("text", ""), (r["id"], p))
                    continue
                self.assertEqual(s["value"], SL.disp(v["si"], p), (r["id"], p))
                if s["range"] and not v.get("range_own"):
                    self.assertTrue(s["range_keys"], (r["id"], p))
                    self.assertEqual(s["range_status"], "unchecked", (r["id"], p))

    def test_links_exist_and_are_narrow(self):
        ids = {e["id"] for e in KP.entries("de")}
        for r in M.materials():
            e = KP.entry("material:" + r["id"], "de")
            for x in e["links"]["atlas"] + e["links"]["mech"]:
                self.assertIn(x["id"], ids, r["id"])
            if str(r["id"]).startswith(("en-aw-6", "en-aw-7")):
                self.assertNotIn("mech:ausscheidung", {x["id"] for x in e["links"]["mech"]}, r["id"])

    def test_search_finds_material_entries(self):
        for r in M.materials()[::9]:
            hits = {x["id"] for g in F.search(M.summary(r, "de")["name"], "de", 200, ["entry"])["groups"] for x in g["items"]}
            self.assertIn("material:" + r["id"], hits)
        mat = next(g for g in F.search("42CrMo4", "de", 8)["groups"] if g["kind"] == "material")
        self.assertTrue(mat["items"][0]["act"]["kp"].startswith("material:"))

    def test_index_is_navigable(self):
        ix = KP.index("en")
        self.assertEqual(len(ix), 195)
        mats = [x for x in ix if x["kind"] == "material"]
        self.assertTrue(all(x["group"] and x["sub"] for x in mats))
        self.assertGreater(len({x["sub"] for x in mats}), 3)
        self.assertTrue(any(x["open"] for x in ix))


class IndexValueToField(unittest.TestCase):
    def run_(self, **q):
        return T.run("einheit", q, T.Ctx())

    def test_converts(self):
        self.assertAlmostEqual(self.run_(value=2.1, **{"from": "GPa", "to": "MPa"})["value"], 2100)
        self.assertAlmostEqual(self.run_(value=20, **{"from": "°C", "to": "K"})["value"], 293.15)
        self.assertAlmostEqual(self.run_(value=10, **{"from": "MPa·m^0.5", "to": "MPa√m"})["value"], 10)
        r = self.run_(value=1000, u=10, **{"from": "MPa", "to": "GPa"})
        self.assertAlmostEqual(r["value"], 1)
        self.assertAlmostEqual(r["u"], 0.01)
        self.assertFalse(self.run_(value=3, **{"from": "mm", "to": "mm"})["converted"])

    def test_refuses_a_dimension_mismatch(self):
        for a, b in (("MPa", "mm"), ("%", ""), ("°", ""), ("MPa", ""), ("", "MPa"), ("h", "°C")):
            with self.assertRaises(T.ToolError, msg=(a, b)):
                self.run_(value=1, **{"from": a, "to": b})
        with self.assertRaises(T.ToolError):
            self.run_(value="abc", **{"from": "MPa", "to": "MPa"})


class Page(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.page = Path(PAGE).read_text(encoding="utf-8")

    def test_decoder_text_left_the_card_and_structure(self):
        for gone in ("strDec", "decHtml", 'decodeHtml(dec, "dec")', 'decodeHtml(d, "decs")'):
            self.assertNotIn(gone, self.page)
        self.assertIn('id="decQ"', self.page)                  # die Eingabe bleibt als Werkzeug
        self.assertGreaterEqual(self.page.count('data-kp="material:'), 3)

    def test_index_take_is_wired(self):
        self.assertIn("LabIndex.browse(api, toast, takeIndex)", self.page)
        self.assertIn("api/tool/einheit", self.page)

    def test_views_no_longer_carry_explanations(self):
        for spec in list(VW.V.values()) + [VW.S_CAT]:
            for sp in spec.values():
                self.assertEqual(len(sp), 1)


if __name__ == "__main__":
    unittest.main()
