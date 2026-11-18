"""Molekülkarte im Bericht (ER-401) und Strukturbild als Vektorgrafik (ER-402)."""
import base64
import unittest

from elementrechner import bundle as B
from elementrechner import structure as ST


def molfile(atoms, bonds):
    """atoms: [(el, x, y, charge)], bonds: [(a, b, order, stereo)] (1-basiert) -> V2000 mit M  CHG."""
    out = ["", "  test", "", f"{len(atoms):3d}{len(bonds):3d}  0  0  0  0  0  0  0  0999 V2000"]
    for el, x, y, _q in atoms:
        out.append(f"{x:10.4f}{y:10.4f}{0:10.4f} {el:<3} 0  0  0  0  0  0  0  0  0  0  0  0")
    for a, b, o, s in bonds:
        out.append(f"{a:3d}{b:3d}{o:3d}{s:3d}")
    ch = [(i + 1, q) for i, (_e, _x, _y, q) in enumerate(atoms) if q]
    if ch:
        out.append("M  CHG" + f"{len(ch):3d}" + "".join(f" {i:3d} {q:3d}" for i, q in ch))
    out.append("M  END")
    return "\n".join(out)


ETHANOL = molfile([("C", 0, 0, 0), ("C", 1.3, 0.75, 0), ("O", 2.6, 0, 0)], [(1, 2, 1, 0), (2, 3, 1, 0)])
GLY_ZW = molfile([("N", 0, 0, 1), ("C", 1.3, 0.75, 0), ("C", 2.6, 0, 0), ("O", 2.6, -1.5, 0), ("O", 3.9, 0.75, -1)],
                 [(1, 2, 1, 0), (2, 3, 1, 0), (3, 4, 2, 0), (3, 5, 1, 0)])
# (R/S egal) Alanin mit Keil und Strichkeil
ALA = molfile([("C", 0, 0, 0), ("C", 1.3, 0.75, 0), ("N", 1.3, 2.25, 0), ("C", 2.6, 0, 0), ("O", 2.6, -1.5, 0),
               ("O", 3.9, 0.75, 0), ("H", 0.4, 1.6, 0)],
              [(2, 1, 1, 1), (2, 3, 1, 0), (2, 4, 1, 0), (4, 5, 2, 0), (4, 6, 1, 0), (2, 7, 1, 6)])


class Structure(unittest.TestCase):
    def test_labels_and_charges(self):
        m = ST.parse_molfile(GLY_ZW)
        self.assertEqual([a["charge"] for a in m["atoms"]], [1, 0, 0, 0, -1])
        labs = [ST.label(m, i) for i in range(5)]
        self.assertEqual(labs, ["NH$_{3}^{+}$", None, None, "O", "O$^{-}$"])
        e = ST.parse_molfile(ETHANOL)
        self.assertEqual([ST.label(e, i) for i in range(3)], [None, None, "OH"])
        a = ST.parse_molfile(ALA)
        self.assertEqual(ST.label(a, 2), "NH$_{2}$")
        self.assertEqual(ST.label(a, 5), "OH")
        self.assertEqual([b["stereo"] for b in a["bonds"]][0], 1)

    def test_old_style_charge_field(self):
        t = GLY_ZW.replace("M  CHG", "X  CHG")                         # ohne M  CHG -> Ladung aus Atomzeile
        lines = t.split("\n")
        lines[4] = lines[4][:36] + "  3" + lines[4][39:]               # 3 = +1 im alten Feld
        self.assertEqual(ST.parse_molfile("\n".join(lines))["atoms"][0]["charge"], 1)

    def test_vector_pdf(self):
        import io
        fig = ST.draw(ALA)
        buf = io.BytesIO()
        fig.savefig(buf, format="pdf")
        pdf = buf.getvalue()
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertNotIn(b"/Subtype /Image", pdf)                          # keine Rastergrafik

    def test_refuses_non_molfile(self):
        with self.assertRaises(ST.MolfileError):
            ST.parse_molfile("CCO")


class Report(unittest.TestCase):
    def _files(self, d):
        return d["files"]

    def test_molecule_card(self):
        ocl = {"logP": -0.31, "logS": 0.6, "tpsa": 20.23, "hbd": 1, "hba": 1, "rot": 0, "stereo": 0}
        for lang in ("de", "en"):
            d = B.build({"state": {"design": {"smiles": "CCO", "molfile": ETHANOL, "ocl": ocl,
                                              "names": {"de": "Ethanol", "en": "ethanol",
                                                        "src": "nach Regeln erzeugt (IUPAC 2013)"}}}}, lang)
            ids = {i.get("id") for i in d["items"]}
            self.assertTrue({"molekuel", "struktur", "molekuel-kennwerte"} <= ids, ids)
            f = d["files"]
            self.assertIn("fig/struktur.pdf", f)
            self.assertNotIn(b"/Subtype /Image", base64.b64decode(f["fig/struktur.pdf"]))
            tex = {k: base64.b64decode(v).decode("utf-8") for k, v in f.items() if k.endswith(".tex")}
            for name, t in tex.items():
                self.assertFalse([c for c in t if ord(c) > 255], f"{lang} {name}: ausserhalb Latin-1")
                for bad in ("\\ce{", "\\tfrac", "\\boldsymbol", "\\text{"):
                    self.assertNotIn(bad, t)
                self.assertEqual(t.count("$") % 2, 0, f"{lang} {name}")
            tab = tex["molekuel-kennwerte.tex"]
            est = "Schätzung" if lang == "de" else "estimate"
            self.assertIn(r"\textit{%s}" % est, tab)
            self.assertIn("er-sander2015", tab)                                 # log P mit Quelle
            self.assertIn("er-joback1987", tab)                                 # Joback-Schätzungen gekennzeichnet
            self.assertIn("er-domalski1993", tab)                               # Benson (ER-404) mit Quelle
            self.assertIn("-234{,}5" if lang == "de" else "-234.5", tab)        # ΔfH°(g) Ethanol nach Benson
            self.assertIn("Benson", tab)
            self.assertIn("er-favre2014", tex["text-molekuel.tex"])              # Regelname zitiert
            self.assertIn("46{,}06" if lang == "de" else "46.06", tex["text-molekuel.tex"])

    def test_zwitterion_without_molfile(self):
        d = B.build({"state": {"design": {"smiles": "[NH3+]CC(=O)[O-]", "names": {"de": "Glycin", "src": "Sammlung"}}}},
                    "de")
        ids = {i.get("id") for i in d["items"]}
        self.assertIn("molekuel", ids)
        self.assertNotIn("struktur", ids)                                      # ohne Koordinaten kein Bild


if __name__ == "__main__":
    unittest.main()
