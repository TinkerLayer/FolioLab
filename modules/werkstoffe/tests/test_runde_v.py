"""Eigenschaftsdiagramm: Übersicht nur Punkte, Spanne erst bei Wahl, Familienumrisse; der Bericht folgt der Ansicht."""
import os
import sys
import unittest

sys.path[:0] = [os.path.join(os.path.dirname(__file__), ".."), os.path.join(os.path.dirname(__file__), "..", "..", "..", "sdk", "python")]

from werk import bundle as B  # noqa: E402
from werk import charts as CH  # noqa: E402
from werk import select as SL  # noqa: E402
from werk import tools as T  # noqa: E402


def _req(view=None):
    return {"x": "rho", "y": "E", "index": "beam_E", "lang": "de", **({"view": view} if view is not None else {})}


class MethodsFollowThePieces(unittest.TestCase):
    def test_each_tool_names_its_methods_step(self):
        secs = [{"tool": "weibull", "req": {"values": [300, 320, 340, 355, 370, 390]}},
                {"tool": "haerte", "req": {"method": "HV", "indents": [{"F": 98.07, "d1": 0.43}, {"F": 98.07, "d1": 0.44}]}}]
        b = B.build({"sections": secs, "lang": "de"}, T.Ctx(), {})
        pieces = [i for i in b["items"] if i["kind"] in ("figure", "table") and i["id"].startswith(("weibull", "haerte"))]
        self.assertTrue(pieces)
        for it in pieces:
            with self.subTest(it=it["id"]):
                self.assertEqual(it["needs"]["steps"], [it["id"].split("-")[0]])
        meth = next(i for i in b["items"] if i["kind"] == "text" and i.get("methods"))
        tagged = {s.get("of") for s in meth["steps"]}
        self.assertTrue({"weibull", "haerte"} <= tagged, tagged)
        self.assertTrue(any(s["id"] == "software" and not s.get("of") for s in meth["steps"]))


class PropertyChartView(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.res = T.run("auswahl", _req(), T.Ctx())
        cls.steel = next(p for p in cls.res["points"] if p["familie"] == "Stahl")

    def test_every_family_has_a_display_name(self):
        fams = {p["familie"] for p in self.res["points"] if p["familie"]}
        self.assertEqual(set(self.res["families"]), fams)
        for f in fams:
            with self.subTest(f=f):
                self.assertIn(f, SL.FAMILY_NAMES)
                self.assertNotEqual(SL.family_name(f, "en"), "")
        self.assertEqual(SL.family_name("Stahl", "en"), "Steels")
        self.assertEqual(SL.family_name("unbekannt"), "unbekannt")

    def _artists(self, view):
        fig = CH.fig_ashby(self.res, "de", view=view)
        ax = fig.axes[0]
        return ax, [c for c in ax.collections if len(c.get_offsets()) and c.get_sizes().size and c.get_sizes()[0] > 0]

    def test_overview_draws_dots_only(self):
        ax, dots = self._artists({})
        self.assertEqual(len(ax.patches), 0)                                  # keine Spannen-Rechtecke
        self.assertEqual(len([c for c in ax.collections if type(c).__name__ == "LineCollection"]), 0)  # keine Fehlerbalken
        self.assertGreaterEqual(sum(len(c.get_offsets()) for c in dots), len(self.res["points"]))

    def test_selection_shows_its_range(self):
        ax, _ = self._artists({"sel": self.steel["id"]})
        self.assertEqual(len(ax.patches), 1)
        self.assertIn(self.steel["name"], [t.get_text() for t in ax.texts])

    def test_groups_hide_dots_until_a_family_is_chosen(self):
        ax, dots = self._artists({"groups": True})
        n_fam = len({p["familie"] for p in self.res["points"] if p["familie"]})
        self.assertEqual(len(ax.patches), n_fam)                              # ein Umriss je Familie
        self.assertEqual(sum(len(c.get_offsets()) for c in dots), 0)         # keine sichtbaren Punkte
        ax, dots = self._artists({"groups": True, "fam": "Stahl"})
        n_steel = sum(1 for p in self.res["points"] if p["familie"] == "Stahl")
        self.assertEqual(sum(len(c.get_offsets()) for c in dots), n_steel)

    def test_report_caption_follows_the_view(self):
        def cap(view):
            b = B.build({"sections": [{"tool": "auswahl", "req": _req(view)}], "lang": "de"}, T.Ctx(), {})
            return next(i["caption"] for i in b["items"] if i["kind"] == "figure")
        self.assertNotIn("Spanne", cap({}))
        self.assertIn("mit seiner Spanne", cap({"sel": self.steel["id"]}))
        c = cap({"groups": True, "fam": "Stahl"})
        self.assertIn("Werkstofffamilie", c)
        self.assertIn("Stähle", c)


if __name__ == "__main__":
    unittest.main()
