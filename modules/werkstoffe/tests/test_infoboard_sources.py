"""Sources on the compendium and the info board: one standard counts once, the check note follows the language,
and a family chart cites the materials its outlines are drawn from."""
import base64
import sys
import unittest
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

from werk import bundle as B, infoboard as IB, kompendium as KP, tools as T  # noqa: E402

REQ = {"x": "rho", "y": "E", "classes": [], "mp": False, "limits": [], "index": "beam_E"}


def chart(view, limits=None):
    return IB.make_pin({"kind": "figure", "fig": "chart", "req": REQ, "view": view, "limits": limits}, thumb=False)


def build(board, lang="de"):
    req = {"sections": [{"tool": "infotafel", "req": {"board": board, "frame": None, "leave_out": []}}], "lang": lang, "include": {}, "title": None}
    return B.build(req, T.Ctx(), {})


def tex(bundle):
    return "\n".join(base64.b64decode(v).decode("utf-8") for k, v in bundle["files"].items() if k.endswith(".tex"))


class SameSourceTest(unittest.TestCase):
    def test_no_entry_lists_a_source_twice(self):
        for e in KP.index("de"):
            with self.subTest(e["id"]):
                seen = Counter(q["text"] for q in KP.entry(e["id"], "de")["refs"])
                self.assertEqual([t for t, n in seen.items() if n > 1], [])

    def test_range_standard_uses_the_register_key(self):
        self.assertEqual(KP._same_source("en10083_3"), "en-10083-3")
        self.assertEqual(KP._same_source("not-a-source"), "not-a-source")


class NoteLanguageTest(unittest.TestCase):
    def test_check_note_follows_the_language(self):
        en = [q["text"] for q in KP.entry("material:42crmo4-qt", "en")["refs"] if q["unchecked"]]
        de = [q["text"] for q in KP.entry("material:42crmo4-qt", "de")["refs"] if q["unchecked"]]
        self.assertTrue(en and de)
        self.assertFalse(any(KP.RF.NG in t for t in en))
        self.assertTrue(all(KP.NG_EN in t for t in en))
        self.assertTrue(all(KP.RF.NG in t for t in de))

    def test_english_board_bibliography(self):
        pin = IB.make_pin({"kind": "entry", "id": "material:42crmo4-qt"}, thumb=False)
        board = {"id": "b", "name": "T", "frames": [], "cards": [{**pin, "x": 0, "y": 0, "w": 260, "h": 80}]}
        bib = base64.b64decode(build(board, "en")["files"]["refs.bib"]).decode("utf-8")
        self.assertNotIn(KP.RF.NG, bib)
        self.assertIn(KP.NG_EN, bib)


class FamilyChartTest(unittest.TestCase):
    def test_outlines_count_as_shown(self):
        pin = chart({"groups": True})
        cap = pin["content"]["de"]["figure"]["caption"]
        self.assertIn("Umrisse von", cap)
        self.assertNotIn(" 0 Werkstoffe", cap)
        self.assertEqual(set(pin["sources"]), set(chart({"groups": False})["sources"]))

    def test_view_limits_still_narrow_the_sources(self):
        everything, part = chart({"groups": True}), chart({"groups": True}, [7.0, 9.0, 150.0, 250.0])
        self.assertLess(len(part["sources"]), len(everything["sources"]))


class MethodsTest(unittest.TestCase):
    def test_one_sentence_for_all_frames(self):
        pin = IB.make_pin({"kind": "entry", "id": "material:42crmo4-qt"}, thumb=False)
        frames = [{"id": f, "name": f, "x": 900 * k, "y": 0, "w": 800, "h": 600} for k, f in enumerate(("A", "B", "C"))]
        cards = [{**pin, "id": f"c{k}", "x": 900 * k + 10, "y": 10, "w": 260, "h": 80, "frame": f["id"]} for k, f in enumerate(frames)]
        files = build({"id": "b", "name": "T", "frames": frames, "cards": cards})["files"]
        body = base64.b64decode(files["text-methodik.tex"]).decode("utf-8")           # methods/s1.tex is the same step
        self.assertEqual(body.count("aus dem Kompendium des Moduls Werkstoffe"), 1)


if __name__ == "__main__":
    unittest.main()
