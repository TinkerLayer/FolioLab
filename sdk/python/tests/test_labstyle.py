"""labstyle: style specs for report figures."""
import base64
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

import labstyle as S  # noqa: E402
from labbundle import Bundle  # noqa: E402


def fig2():
    fig, ax = plt.subplots(figsize=(6, 4))
    x = np.linspace(0, 10, 30)
    ax.plot(x, x, label="A")
    ax.plot(x, 2 * x, label="B")
    ax.legend()
    ax.set_title("T")
    return fig


class StyleTest(unittest.TestCase):
    def test_clean_rejects_bad_values(self):
        s = S.clean({"width_mm": 9999, "font": "comic;}", "series": {"x": {"color": "url(javascript:1)", "lw": 99}},
                     "legend": {"loc": "nowhere"}, "axes": [{"xlim": ["a", 3], "xscale": "sqrt"}], "preset": "nope",
                     "elements": {"bad key": {"hidden": True}, "0.line1": {"alpha": 7, "color": "x("}},
                     "colors": {"grid": "#12", "text": "#123456", "evil": "#000000"}, "crop": [0.9, -1, "a", 0.1]})
        self.assertEqual(s, {"width_mm": 400, "series": {"x": {"lw": 8}}, "axes": [{"xlim": [None, 3.0]}],
                             "elements": {"0.line1": {"alpha": 1.0}}, "colors": {"text": "#123456"},
                             "crop": [0.45, 0.0, 0.0, 0.1]})

    def test_elements_listed_and_styled(self):
        fig, ax = plt.subplots(figsize=(6, 4))
        x = np.linspace(0, 10, 30)
        ax.plot(x, x, label="A")
        ax.axhline(3, color="grey")
        ax.axvspan(2, 3, color="yellow")
        ax.scatter([1], [1], label="P")
        ax.annotate("Max 10", (10, 10), xytext=(5, 9), arrowprops={"arrowstyle": "->"})
        ax.bar([4], [2], label="Bar")
        ax.legend()
        els = {e["key"]: e for e in S.describe(fig)["elements"]}
        self.assertEqual(set(els), {"0.line:A", "0.line0", "0.patch0", "0.coll:P", "0.text0", "0.bars:Bar"})
        self.assertEqual(els["0.line0"]["text"], "horizontal line at 3")
        self.assertEqual(els["0.text0"]["kind"], "label")
        S.apply(fig, {"elements": {"0.line0": {"hidden": True}, "0.text0": {"text": "Max", "color": "#ff0000"},
                                   "0.patch0": {"color": "#00ff00", "alpha": 0.5}, "0.coll:P": {"hidden": True},
                                   "0.bars:Bar": {"label": "Balken"}},
                      "colors": {"background": "#eeeeee", "text": "#0000aa", "axes": "#00aa00"}})
        self.assertFalse(ax.get_lines()[1].get_visible())
        self.assertEqual(ax.texts[0].get_text(), "Max")
        self.assertEqual(ax.texts[0].get_color(), "#ff0000")
        span = [p for p in ax.patches if p.get_facecolor()[:3] == (0.0, 1.0, 0.0)]
        self.assertEqual(len(span), 1)
        self.assertEqual(span[0].get_alpha(), 0.5)
        self.assertEqual([t.get_text() for t in ax.get_legend().get_texts()], ["A", "Balken"])
        self.assertEqual(ax.xaxis.label.get_color(), "#0000aa")

    def test_fonts_cm_and_missing(self):
        f = fig2()
        S.apply(f, {"font": "cm"})
        self.assertEqual(f.axes[0].xaxis.label.get_fontfamily()[0], "cmr10")
        used = S.apply(fig2(), {"font": "No Such Font 123"})
        self.assertTrue(used["notes"])
        self.assertIn("cmr10", S.font_names())

    def test_crop_and_boxes(self):
        f = fig2()
        full = S.frame(f)
        cut = S.frame(f, [0.1, 0, 0, 0.2])
        self.assertAlmostEqual(cut.width, full.width * 0.9, places=6)
        self.assertAlmostEqual(cut.height, full.height * 0.8, places=6)
        (b,) = S.boxes(f, full)
        x0, y0, x1, y1 = b["box"]
        self.assertTrue(0 < x0 < x1 < 1 and 0 < y0 < y1 < 1)
        self.assertEqual(b["xlim"], list(f.axes[0].get_xlim()))

    def test_preset_gives_size_and_fonts(self):
        f = fig2()
        used = S.apply(f, {"preset": "elsevier-1"})
        self.assertAlmostEqual(f.get_size_inches()[0] * 25.4, 90, places=3)
        self.assertEqual(used["font_size"], 7)
        self.assertEqual(f.axes[0].title.get_fontsize(), 8)
        self.assertEqual(f.axes[0].xaxis.label.get_fontsize(), 7)

    def test_series_hide_colour_rename_and_axes(self):
        f = fig2()
        S.apply(f, {"series": {"A": {"hidden": True}, "B": {"color": "#ff0000", "label": "Neu"}},
                    "axes": [{"xlabel": "x [mm]", "xlim": [0, 5], "yscale": "log", "xticks": 3}], "title": ""})
        ax = f.axes[0]
        a, b = ax.get_lines()
        self.assertFalse(a.get_visible())
        self.assertEqual(b.get_color(), "#ff0000")
        self.assertEqual([t.get_text() for t in ax.get_legend().get_texts()], ["Neu"])
        self.assertEqual(ax.get_xlabel(), "x [mm]")
        self.assertEqual(ax.get_xlim(), (0.0, 5.0))
        self.assertEqual(ax.get_yscale(), "log")
        self.assertEqual(ax.get_title(), "")

    def test_legend_off_and_palette(self):
        f = fig2()
        S.apply(f, {"legend": {"show": False}, "palette": "okabe-ito"})
        self.assertIsNone(f.axes[0].get_legend())
        self.assertEqual(f.axes[0].get_lines()[1].get_color(), S.PALETTES["okabe-ito"][1])

    def test_bundle_restyles_only_the_named_figure(self):
        def build(styles, desc=False):
            b = Bundle("x", "X", "T", "de")
            b.add_figure(fig2(), "a", "A")
            b.add_figure(fig2(), "b", "B")
            b.set_source({"styles": styles, "describe_figures": desc} if styles is not None else {}, {})
            return b.to_dict()
        plain, styled = build(None), build({"a": {"preset": "nature-1"}})
        self.assertNotEqual(plain["files"]["fig/a.png"], styled["files"]["fig/a.png"])
        self.assertEqual(plain["files"]["fig/b.png"], styled["files"]["fig/b.png"])
        self.assertEqual(styled["items"][0]["style"]["width_mm"], 89)
        self.assertNotIn("style", plain["items"][0])
        self.assertTrue(base64.b64decode(styled["files"]["fig/a.pdf"]).startswith(b"%PDF"))
        it = build({"a": {"preset": "nature-1", "crop": [0, 0, 0.2, 0]}}, desc=True)["items"][0]
        self.assertEqual([s["label"] for s in it["describe"]["series"]], ["A", "B"])
        now = it["describe"]["now"]
        self.assertEqual(now["width_mm"], 89)
        self.assertEqual(len(now["axes"]), 1)
        self.assertGreater(now["axes"][0]["box"][2], 0.9)     # the right side is cut, the plot reaches the edge

    def test_groups_by_kind_and_element_override(self):
        fig, ax = plt.subplots(figsize=(6, 4))
        x = np.linspace(0, 10, 30)
        ax.plot(x, x, label="A")
        ax.plot(x, 2 * x, label="B")
        ax.plot([1, 2], [1, 2], "o")                       # markers only
        ax.text(1, 1, "one")
        ax.text(2, 2, "two")
        ax.set_xlabel("x")
        ax.set_ylabel("y")
        ax.legend()
        d = S.describe(fig)
        groups = {e["key"]: e["group"] for e in d["elements"]}
        self.assertEqual(groups, {"0.line:A": "lines", "0.line:B": "lines", "0.line0": "markers",
                                  "0.text0": "annotations", "0.text1": "annotations"})
        self.assertEqual(d["groups"]["series_names"], 2)
        self.assertEqual(d["groups"]["axis_labels"], 2)
        self.assertEqual({e["key"]: e.get("raw") for e in d["elements"]}["0.text1"], "two")
        spec = {"groups": {"lines": {"color": "#ff0000", "lw": 3, "hidden": True}, "annotations": {"size": 14, "bold": True},
                           "axis_labels": {"color": "#00ff00"}, "tick_labels": {"size": 5}, "series_names": {"color": "#0000ff"},
                           "markers": {"lw": 9}},                     # lw is not a marker prop: dropped
                "elements": {"0.line:B": {"hidden": False, "lw": 1}}}
        self.assertNotIn("markers", S.clean(spec)["groups"])
        S.apply(fig, spec)
        a, b, m = ax.get_lines()
        self.assertFalse(a.get_visible())
        self.assertTrue(b.get_visible())                    # shown although its kind is hidden
        self.assertEqual((b.get_color(), b.get_linewidth()), ("#ff0000", 1))
        self.assertTrue(all(t.get_fontsize() == 14 and t.get_fontweight() == "bold" for t in ax.texts))
        self.assertEqual(ax.xaxis.label.get_color(), "#00ff00")
        self.assertEqual(ax.get_xticklabels()[0].get_fontsize(), 5)
        self.assertEqual([t.get_text() for t in ax.get_legend().get_texts()], ["B"])
        self.assertTrue(all(t.get_color() == "#0000ff" for t in ax.get_legend().get_texts()))

    def test_tag_and_preview_mode(self):
        f = fig2()
        f.axes[0].text(1, 1, "note")
        ids = S.tag(f)
        self.assertEqual(ids["0.line:A"], ["cel0"])
        self.assertEqual(ids["@xlabel0"], ["cax0x"])
        self.assertEqual(f.axes[0].get_lines()[1].get_gid(), "cel1")
        b = Bundle("x", "X", "T", "de")
        b.add_figure(fig2(), "a", "A")
        b.add_figure(fig2(), "b", "B")
        b.set_source({"describe_figures": True, "styles": {"a": {"groups": {"lines": {"lw": 3}}}},
                      "preview": {"item": "a", "svg": True}}, {})
        out = b.to_dict()
        self.assertEqual(sorted(out["files"]), ["fig/a.svg"])   # only the edited figure, no PDF or PNG
        svg = base64.b64decode(out["files"]["fig/a.svg"]).decode()
        self.assertIn('id="cel0"', svg)
        self.assertIn(">T</text>", svg)                       # texts stay text
        now = out["items"][0]["describe"]["now"]
        self.assertEqual(now["gids"]["0.line:B"], ["cel1"])
        self.assertNotIn("describe", out["items"][1])

    def test_hidden_part_gives_its_axis_range_back(self):
        def drawn():
            fig, ax = plt.subplots()
            x = np.linspace(0, 10, 30)
            ax.plot(x, 14 * x)
            S.mark(ax.plot(x * 3, 60 * x), "feld")
            ax.axvline(25)                                     # height not in data units: no say in the y range
            ax.set_xlim(0, 30)
            ax.set_ylim(0, 600)
            return fig, ax
        fig, ax = drawn()
        S.apply(fig, {"parts": {"feld": {"hidden": True}}})
        self.assertEqual(ax.get_ylim()[0], 0)                  # the zero line stays
        self.assertLess(ax.get_ylim()[1], 160)
        self.assertGreaterEqual(ax.get_ylim()[1], 140)
        plt.close(fig)
        fig, ax = drawn()                                      # a limit set by hand wins
        S.apply(fig, {"parts": {"feld": {"hidden": True}}, "axes": [{"ylim": [None, 500]}]})
        self.assertEqual(ax.get_ylim(), (0, 500))
        plt.close(fig)
        fig, ax = plt.subplots()                               # reversed axis (wavenumbers) stays reversed
        ax.plot([4000, 2000], [0, 1])
        S.mark(ax.plot([4000, 400], [0, 1]), "x")
        ax.set_xlim(4000, 400)
        S.apply(fig, {"parts": {"x": {"hidden": True}}})
        self.assertEqual(ax.get_xlim()[0], 4000)
        self.assertGreater(ax.get_xlim()[1], 1800)
        self.assertLess(ax.get_xlim()[1], 2000)
        plt.close(fig)

    def test_figures_written_when_the_bundle_is_built(self):
        b = Bundle("x", "X", "T", "de")
        f = fig2()
        b.add_figure(f, "a", "A")
        self.assertNotIn("fig/a.pdf", b.files)                # drawn once, at to_dict
        out = b.to_dict()
        self.assertTrue(base64.b64decode(out["files"]["fig/a.pdf"]).startswith(b"%PDF"))
        self.assertTrue(base64.b64decode(out["files"]["fig/a.png"]).startswith(b"\x89PNG"))


if __name__ == "__main__":
    unittest.main()
