"""labbundle: Text für LaTeX (tex_escape), Zitierhilfen."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from labbundle import cite, cite_keys, tex_escape  # noqa: E402


class TexEscapeTest(unittest.TestCase):
    def test_superscript_runs_are_one_group(self):
        self.assertEqual(tex_escape("10⁻⁶ m²/s"), "10$^{-6}$ m$^2$/s")
        self.assertEqual(tex_escape("x²³"), "x$^{23}$")

    def test_subscripts(self):
        self.assertEqual(tex_escape("CO₂, Al₂O₃"), "CO$_2$, Al$_2$O$_3$")
        self.assertEqual(tex_escape("C₁₂"), "C$_{12}$")

    def test_specials(self):
        self.assertEqual(tex_escape("50 % & #1_a"), r"50 \% \& \#1\_a")
        self.assertEqual(tex_escape("a < b ⇌ c"), r"a $<$ b $\rightleftharpoons$ c")

    def test_cite(self):
        self.assertEqual(cite_keys(["a", "b,c"], "a", None), ["a", "b", "c"])
        self.assertEqual(cite(["x", "y"]), r"~\cite{x,y}")
        self.assertEqual(cite([]), "")


if __name__ == "__main__":
    unittest.main()
