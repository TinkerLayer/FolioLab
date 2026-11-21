"""labbundle/labstyle: parts of a figure. A piece cites and describes only what it shows: the caption, its citations
and the methods steps a figure needs follow the parts that are still visible after a style spec."""
import base64
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

import labstyle  # noqa: E402
from labbundle import Bundle, _untag, compose_caption, join_list, step_tag  # noqa: E402

PARTS = [
    {"id": "envelope", "label": "Hüllkurve", "cites": ["fit-src"], "steps": ["fit"], "caption": "die Hüllkurve"},
    {"id": "ref", "label": "Referenz S235", "cites": ["mat-s235"], "steps": ["vergleich"],
     "note": "Grau: Referenzkurve S235."},
    {"id": "peaks", "label": "Spitzen", "match": ["*.line:Spitzen*"], "steps": ["peaks"]},
]


def draw():
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.plot([0, 1, 2], [0, 2, 1], label="Messkurve")
    labstyle.mark(ax.plot([0, 2], [2, 1.2], "--", label="Hüllkurve: Gerade"), "envelope")
    labstyle.mark(ax.plot([0, 2], [0, 1.5], label="Referenz S235"), "ref")
    labstyle.mark(ax.annotate("S235", (2, 1.5)), "ref")
    ax.plot([1], [2], "o", label="Spitzen")
    ax.legend()
    return fig


def bundle(styles=None):
    b = Bundle(module="zugversuch", module_name="Zugversuch", title="T", lang="de", slug="t")
    b.add_figure(draw, "kurve", "Verlauf der Messung{parts}.", cites=["data"], parts=PARTS, steps=["messung"])
    b.add_table("kennwerte", "x", "Kennwerte.", steps=["fit"])
    b.add_values([("Rm", "Rm", "1", "1"), ("n", "n", "2", "2")], needs={"Rm": ["fit"]})
    b.add_methods([{"id": "messung", "text": "Gemessen wurde nach ISO~6892-1."}, {"id": "fit", "text": "Ausgleich."},
                   {"id": "vergleich", "text": r"Vergleich~\cite{mat-s235}."}],
                  "Methodik", sep=" ", brief="Gemessen wurde an einer Probe; " + b.software_clause() + ".")
    if styles:
        b.set_source({"styles": styles}, {})
    return b.to_dict()


def item(d, iid):
    return next(i for i in d["items"] if i.get("id") == iid)


class ComposeCaptionTest(unittest.TestCase):
    def test_join_and_fragments(self):
        self.assertEqual(join_list(["A", "B", "C"], "de"), "A, B und C")
        self.assertEqual(join_list(["A", "B"], "en"), "A and B")
        parts = [dict(p, match=[]) for p in PARTS]
        for p in parts:
            p.setdefault("caption", "")
            p.setdefault("note", "")
            p.setdefault("cites", [])
        cap, keys = compose_caption("Verlauf{parts}.", ["data"], parts)
        self.assertEqual(cap, r"Verlauf mit die Hüllkurve~\cite{fit-src}~\cite{data}. Grau: Referenzkurve S235~\cite{mat-s235}.")
        self.assertEqual(keys, ["data", "fit-src", "mat-s235"])
        cap, keys = compose_caption("Verlauf{parts}.", ["data"], parts, {"envelope": False, "ref": False})
        self.assertEqual(cap, r"Verlauf~\cite{data}.")
        self.assertEqual(keys, ["data"])


class PartsTest(unittest.TestCase):
    def test_declared_figure_lists_parts_and_needs(self):
        d = bundle()
        f = item(d, "kurve")
        self.assertEqual(f["needs"], {"steps": ["messung"]})
        self.assertEqual([p["id"] for p in f["parts"]], ["envelope", "ref", "peaks"])
        self.assertNotIn("shown", f["parts"][0])
        self.assertIn("Hüllkurve", f["caption"])
        self.assertEqual(f["cites"], ["data", "fit-src", "mat-s235"])
        self.assertEqual(item(d, "kennwerte")["needs"], {"steps": ["fit"]})
        vals = next(i for i in d["items"] if i["kind"] == "values")["values"]
        self.assertEqual(vals[0]["needs"], ["fit"])
        self.assertNotIn("needs", vals[1])

    def test_hidden_part_drops_fragment_note_and_citation(self):
        d = bundle({"kurve": {"parts": {"envelope": {"hidden": True}}}})
        f = item(d, "kurve")
        self.assertNotIn("Hüllkurve", f["caption"])
        self.assertNotIn("fit-src", f["caption"])
        self.assertIn("mat-s235", f["caption"])
        self.assertEqual(f["cites"], ["data", "mat-s235"])
        self.assertEqual([p.get("shown", True) for p in f["parts"]], [False, True, True])
        self.assertIn("Hüllkurve", f["caption_full"])

    def test_element_hidden_in_customise_hides_its_part(self):
        # the reference curve and its label hidden one by one (element keys as describe() lists them)
        d = bundle({"kurve": {"elements": {"0.line:Referenz S#": {"hidden": True}, "0.text0": {"hidden": True}}}})
        f = item(d, "kurve")
        self.assertEqual(f["parts"][1].get("shown"), False)
        self.assertNotIn("Referenzkurve", f["caption"])
        self.assertEqual(f["cites"], ["data", "fit-src"])
        # one of two artists still visible: the part is still shown
        d = bundle({"kurve": {"elements": {"0.text0": {"hidden": True}}}})
        self.assertNotIn("shown", item(d, "kurve")["parts"][1])

    def test_group_hidden_and_match(self):
        d = bundle({"kurve": {"groups": {"markers": {"hidden": True}}}})
        f = item(d, "kurve")
        self.assertEqual(f["parts"][2].get("shown"), False)          # found by its match glob, a marker
        self.assertNotIn("shown", f["parts"][0])

    def test_describe_names_the_part_of_each_element(self):
        d = bundle({"kurve": {}})
        b = Bundle(module="x", module_name="X", title="T", slug="t")
        b.add_figure(draw, "k", "K.", parts=PARTS)
        b.set_source({"describe_figures": True}, {})
        desc = item(b.to_dict(), "k")["describe"]
        parts = {e["key"]: e.get("part") for e in desc["elements"]}
        self.assertEqual(parts["0.line:Hüllkurve: Gerade"], "envelope")
        self.assertEqual(parts["0.text0"], "ref")
        self.assertEqual(parts["0.line:Spitzen"], "peaks")
        self.assertIsNone(parts["0.line:Messkurve"])
        self.assertTrue(d["items"])

    def test_spec_parts_are_cleaned(self):
        self.assertEqual(labstyle.clean({"parts": {"envelope": {"hidden": True}, "x y": {"hidden": True},
                                                   "ref": {"hidden": False}}}), {"parts": {"envelope": {"hidden": True}}})

    def test_brief_step_is_its_own_step_and_not_in_the_full_text(self):
        d = bundle()
        files = {k: base64.b64decode(v).decode("utf-8") for k, v in d["files"].items() if k.endswith((".tex", ".json"))}
        meta = json.loads(files["methods.json"])["steps"]
        self.assertEqual(meta[0]["id"], "kurz")
        self.assertTrue(meta[0]["brief"])
        self.assertFalse(meta[0]["short"])
        self.assertEqual([s["id"] for s in meta[1:]], ["messung", "fit", "vergleich", "software"])
        self.assertNotIn("Probe;", files["text-methodik.tex"])
        self.assertIn(r"ausgewertet mit Folio Lab, Modul", files["methods/kurz.tex"])
        self.assertIn(r"\cite{folio-lab-zugversuch}", files["methods/kurz.tex"])

    def test_a_figure_without_steps_or_parts_stays_undeclared(self):
        b = Bundle(module="x", module_name="X", title="T", slug="t")
        b.add_figure(draw, "plain", "P.")
        b.add_figure(draw, "none", "N.", parts=[])
        b.add_figure(draw, "step", "S.", steps=[])
        d = b.to_dict()
        self.assertNotIn("needs", item(d, "plain"))
        self.assertNotIn("parts", item(d, "plain"))
        self.assertEqual(item(d, "none")["needs"], {"steps": []})
        self.assertEqual(item(d, "step")["needs"], {"steps": []})

    def test_parts_with_the_same_list_share_one_sentence(self):
        parts = [{"id": f"r{i}", "label": n, "cites": [f"mat-{i}"], "steps": [], "caption": "", "note": n, "list": "Grau:",
                  "match": []} for i, n in enumerate(("S235", "S355", "AW-1050"))]
        cap, _ = compose_caption("Verlauf.", [], parts)
        self.assertEqual(cap, r"Verlauf. Grau: S235~\cite{mat-0}, S355~\cite{mat-1} und AW-1050~\cite{mat-2}.")
        cap, keys = compose_caption("Verlauf.", [], parts, {"r1": False})
        self.assertEqual(cap, r"Verlauf. Grau: S235~\cite{mat-0} und AW-1050~\cite{mat-2}.")
        self.assertEqual(keys, ["mat-0", "mat-2"])

    def test_step_marks_change_neither_text_nor_ids(self):
        plain = "Gemessen wurde. Der Ausgleich folgt. Verglichen wurde."
        marked = "Gemessen wurde." + step_tag("fit") + " Der Ausgleich folgt." + step_tag("vergleich") + " Verglichen wurde."
        self.assertEqual(_untag(marked)[0], plain)

        def steps(text):
            b = Bundle(module="zugversuch", module_name="Zugversuch", title="T", lang="de", slug="t")
            b.add_methods([text], "Methodik", sep=" ")
            d = b.to_dict()
            return d, json.loads(base64.b64decode(d["files"]["methods.json"]))["steps"]

        d0, s0 = steps(plain)
        d1, s1 = steps(marked)
        self.assertEqual([s["id"] for s in s1], [s["id"] for s in s0])
        self.assertEqual(d1["files"]["text-methodik.tex"], d0["files"]["text-methodik.tex"])
        self.assertEqual([s.get("of") for s in s1[:3]], [None, "fit", "vergleich"])

    def test_brief_from_takes_the_first_sentence(self):
        b = Bundle(module="zugversuch", module_name="Zugversuch", title="T", lang="de", slug="t")
        text = "Die Probe wurde geprüft." + step_tag("fit") + " Danach folgte der Ausgleich."
        self.assertTrue(b.brief_from(text).startswith("Die Probe wurde geprüft; ausgewertet mit Folio Lab"))
        self.assertTrue(b.brief_from("Die Probe wurde ausgewertet.", evaluated=True)
                        .startswith("Die Probe wurde ausgewertet mit Folio Lab"))

    def test_needs_since_declares_what_a_helper_added(self):
        b = Bundle(module="x", module_name="X", title="T", slug="t")
        b.add_table("vorher", "x", "Davor.")
        b.add_values([("a", "a", "1", "1")])
        mark = b.added_mark()
        b.add_table("budget", "x", "Budget.")
        b.add_table("eigen", "x", "Eigen.", steps=["andere"])
        b.add_values([("u", "u", "2", "2")])
        b.needs_since(mark, ["unsicherheit"])
        d = b.to_dict()
        self.assertNotIn("needs", item(d, "vorher"))
        self.assertEqual(item(d, "budget")["needs"], {"steps": ["unsicherheit"]})
        self.assertEqual(item(d, "eigen")["needs"], {"steps": ["andere"]})
        vals = {v["key"]: v for v in next(i for i in d["items"] if i["kind"] == "values")["values"]}
        self.assertNotIn("needs", vals["a"])
        self.assertEqual(vals["u"]["needs"], ["unsicherheit"])


if __name__ == "__main__":
    unittest.main()
