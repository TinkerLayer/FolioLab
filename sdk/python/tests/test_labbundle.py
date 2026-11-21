"""labbundle: Text für LaTeX (tex_escape), Zitierhilfen."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from labbundle import Bundle, cite, cite_keys, compose_methods, split_sentences, tex_escape  # noqa: E402


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
        self.assertEqual(tex_escape("δν̃ in cm⁻¹"), r"$\delta\tilde{\nu}$ in cm$^{-1}$")   # combining tilde
        self.assertEqual(tex_escape("x̂"), r"$\hat{x}$")

    def test_cite(self):
        self.assertEqual(cite_keys(["a", "b,c"], "a", None), ["a", "b", "c"])
        self.assertEqual(cite(["x", "y"]), r"~\cite{x,y}")
        self.assertEqual(cite([]), "")


class MethodStepsTest(unittest.TestCase):
    def test_sentences_keep_math_braces_and_abbreviations(self):
        t = (r"Die Probe (z.~B. Draht) wurde mit $v = 1.5$ mm/min geprüft. Die Kraft betrug \labval{x}{F}. "
             r"E$_a$ nach Friedman~\cite{f}, vgl. Abb. 3. Kissinger et al. Methode? Fig. 2 zeigt {Eine Sache. Noch} mehr.")
        self.assertEqual(split_sentences(t), [
            "Die Probe (z.~B. Draht) wurde mit $v = 1.5$ mm/min geprüft.", r"Die Kraft betrug \labval{x}{F}.",
            r"E$_a$ nach Friedman~\cite{f}, vgl. Abb. 3.", "Kissinger et al. Methode?", "Fig. 2 zeigt {Eine Sache. Noch} mehr."])

    def test_full_text_unchanged_and_steps_compose(self):
        b = Bundle("x", "X", "T", "de")
        parts = ["Satz eins. Satz zwei~\\cite{a}.\n", "Absatz zwei.\n\nAbsatz drei. Mit zwei Sätzen.\n"]
        b.add_methods(parts, "Methodik", sep="\n", eq="\\[ a=b \\]", software=False)
        self.assertEqual(b.files["text-methodik.tex"].decode(), "\n".join(parts) + "\n\\[ a=b \\]\n")
        it = b.items[-1]
        self.assertTrue(it["methods"])
        steps = it["steps"]
        self.assertEqual([s["id"] for s in steps], ["s1", "s2", "s3", "s4", "s5", "gleichungen"])
        self.assertEqual([s["short"] for s in steps], [True, False, False, False, False, False])
        texts = {s["id"]: b.files[s["file"]].decode() for s in steps}
        self.assertEqual(compose_methods(steps, texts, ["s1", "s2"]), "Satz eins. Satz zwei~\\cite{a}.\n")
        self.assertEqual(compose_methods(steps, texts, ["s1", "s4", "s5"]), "Satz eins.\n\nAbsatz drei. Mit zwei Sätzen.\n")
        self.assertIn(b"methods/s3.tex", b"".join(k.encode() for k in b.files))

    def test_one_paragraph_of_sentences(self):
        b = Bundle("x", "X", "T", "en")
        b.add_methods(["First.", "Second one.", "Third~\\cite{k}."], "Methods", sep=" ")
        self.assertEqual(b.files["text-methodik.tex"].decode(),
                         "First. Second one. Third~\\cite{k}. The analysis used Folio Lab, X module~\\cite{folio-lab-x}.\n")
        steps = b.items[-1]["steps"]
        self.assertEqual({s["par"] for s in steps}, {0})
        self.assertEqual([s["short"] for s in steps], [True, False, False, True])

    def test_short_is_measurement_standard_software(self):
        b = Bundle("zugversuch", "Zugversuch", "T", "de")
        b.add_methods(["Ausgewertet wurde die Probe P1~\\cite{data-p1}. Der Querschnitt betrug 2 mm². "
                       "Kennwerte nach ISO~6892-1 wurden bestimmt. Verglichen wurde mit Werkstoffen~\\cite{mat-a}. "
                       "Die Glättung folgt~\\cite{astm-e1131}."], "Methodik")
        steps = b.items[-1]["steps"]
        short = [s["id"] for s in steps if s["short"]]
        self.assertEqual(short, ["s1", "s3", "software"])
        soft = b.files["methods/software.tex"].decode()
        self.assertRegex(soft, r"^Ausgewertet wurde mit Folio Lab, Modul Zugversuch, Version \d+\.\d+(\.\d+)?~\\cite\{folio-lab-zugversuch\}\.")
        bib = "\n".join(b.bib)
        self.assertIn("@misc{folio-lab-zugversuch", bib)
        self.assertRegex(bib, r"version = \{\d+\.\d+")

    def test_text_naming_folio_lab_and_own_short(self):
        b = Bundle("x", "X", "T", "en")
        b.add_methods([{"id": "a", "text": "Measured.", "short": True}, {"id": "b", "text": "Smoothed."},
                       {"id": "c", "text": "Done with Folio Lab 1.0.", "short": True}], "Methods")
        steps = b.items[-1]["steps"]
        self.assertEqual([s["id"] for s in steps], ["a", "b", "c"])           # no second software sentence
        self.assertEqual([s["short"] for s in steps], [True, False, True])     # the module's own choice
        self.assertNotIn("own_short", steps[0])

if __name__ == "__main__":
    unittest.main()
