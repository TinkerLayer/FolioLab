"""Bundle fuer Folio Lab (folio-lab-bundle/1): Inhalt, Sprache, Vergleich, Neuaufbau aus den Quelldaten."""
import base64
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parents[1] / "sdk" / "python"))

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _input import measurement  # noqa: E402
from labbundle import split_sentences  # noqa: E402
from flps import analyse, bundle  # noqa: E402
from flps.parser import parse_bytes  # noqa: E402

RAW, NAME, REAL = measurement()          # synthetic curve, or FOLIO_ZV_REFERENCE


def _cfg(**kw):
    base = dict(shape="ISO 527-2 Typ 5B", width_mm=2, thickness_mm=0.1, l0_mm=10, speed_mm_min=1,
                displacement_source="traverse", material_ref="EN AW-5052-H38")
    base.update(kw)
    return analyse.Config(**base)


class BundleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = RAW
        cls.f = parse_bytes(cls.raw, NAME)
        cls.r = analyse.run(cls.f, _cfg())
        cls.req = {"items": [{"name": NAME, "config": _cfg().to_dict()}]}

    def test_single_de(self):
        b = bundle.build([self.r], {NAME: self.raw}, self.req, lang="de")
        self.assertEqual(b["format"], "folio-lab-bundle/1")
        self.assertRegex(b["slug"], r"^[a-z0-9-]+$")
        kinds = {i["kind"] for i in b["items"]}
        self.assertTrue({"figure", "table", "values", "data", "citation", "text"} <= kinds)
        for it in b["items"]:
            for key in ("file", "preview"):
                if key in it:
                    self.assertIn(it[key], b["files"])
        values = base64.b64decode(b["files"]["values.tex"]).decode()
        self.assertIn("@misc{iso527-2", base64.b64decode(b["files"]["refs.bib"]).decode())
        if not REAL:
            self.assertIn(r"{Rm}{140\,MPa}", values)                # known answer of the synthetic curve
        self.assertIn(NAME, b["source"]["files"])

    def test_english_and_include(self):
        b = bundle.build([self.r], {}, self.req, lang="en", include={"figures": False, "data": False, "text": False})
        kinds = {i["kind"] for i in b["items"]}
        self.assertNotIn("figure", kinds)
        self.assertNotIn("data", kinds)
        self.assertIn("table", kinds)
        tab = base64.b64decode(b["files"]["kennwerte.tex"]).decode()
        self.assertNotRegex(tab, r"\d,\d")  # Dezimalpunkt im Englischen

    def test_comparison(self):
        r2 = analyse.run(self.f, _cfg(thickness_mm=0.12, material_ref=None))
        r2.name = "Messung B"
        b = bundle.build([self.r, r2], {}, {"items": []}, lang="de")
        self.assertIn("vergleich.tex", b["files"])
        tab = base64.b64decode(b["files"]["vergleich.tex"]).decode()
        self.assertIn("Messung B", tab)
        self.assertIn(r"\toprule", tab)

    def test_material_sources_traceable(self):
        """Jeder Vergleichswerkstoff nennt eine konkrete Quelle (kein pauschales „Literatur, typische Werte“); eine URL
        landet unverändert als url/urldate in der Literaturangabe."""
        from flps import alloys
        from labbundle import Bundle
        al = alloys.load_alloys()
        for a in al:
            self.assertTrue(a.source.strip(), a.name)
            self.assertNotIn("Literatur, typische Werte", a.source, a.name)
            if a.url:
                self.assertTrue(bundle._safe_url(a.url), a.name)
                self.assertRegex(a.accessed, r"^\d{4}-\d{2}-\d{2}$", a.name)
        pa6 = next(a for a in al if a.name == "PA6 konditioniert")
        b = Bundle(module="zugversuch", module_name="Zugversuch", title="t", lang="de")
        bundle._mat_cite(b, pa6, "de")
        bib = "".join(b.bib)
        self.assertIn("url = {" + pa6.url + "}", bib)
        self.assertIn("urldate = {" + pa6.accessed + "}", bib)
        self.assertIn("Ultramid B3K", bib)

    def test_field_labelled_and_sources_cited(self):
        """Jede Kurve im Spannungs-Dehnungs-Feld ist nummeriert und benannt; Bild, Kandidaten und Quellentabelle zitieren
        die Quelle jedes gezeigten Werkstoffs automatisch (Bildunterschrift), refs.bib enthält alle Einträge."""
        from flps.export import charts, report
        members = charts.field_members(self.r)
        self.assertEqual(len(members), len(self.r.alloys))
        fig = charts.chart3(self.r, key="right")
        texts = [t.get_text() for t in fig.findobj(lambda a: hasattr(a, "get_text"))]
        self.assertIn("1  " + charts.short_name(members[0].name), texts)
        self.assertIn(str(len(members)), texts, "Kurvennummer am Ende der letzten Kurve")
        b = bundle.build([self.r], {NAME: self.raw}, self.req, lang="en")
        items = {(i["kind"], i.get("id")): i for i in b["items"]}
        bib = base64.b64decode(b["files"]["refs.bib"]).decode()
        feld = items[("figure", "feld")]
        self.assertEqual(len(feld["cites"]), len(members))
        self.assertIn(r"\cite{mat-", feld["caption"])
        for k in feld["cites"] + items[("figure", "kandidaten")]["cites"]:
            self.assertIn("@misc{" + k + ",", bib)
        tab = items[("table", "werkstoffe")]
        tex = base64.b64decode(b["files"][tab["file"]]).decode()
        self.assertEqual(tex.count(r"\cite{mat-"), len(members))
        self.assertIn("EN AW-1050A, weich", tex)
        self.assertIn("MakeItFrom", bib)
        self.assertIn(r"\cite{mat-", base64.b64decode(b["files"]["text-methodik.tex"]).decode())
        pages = report.build_report(self.r)
        self.assertEqual(len(pages), 5, "vier Seiten plus Quellen der Vergleichswerte")
        self.assertIn("Quellen der Vergleichswerte", [t.get_text() for t in pages[-1].texts])
        for p in pages:
            import matplotlib.pyplot as plt
            plt.close(p)

    def test_plain_field_figure_cites_and_describes_only_the_curve(self):
        """Feld und Referenz abgeschaltet: die reine Messkurve nennt und zitiert keinen Vergleich mehr."""
        full = bundle.build([self.r], {NAME: self.raw}, self.req, lang="de")
        feld = next(i for i in full["items"] if i.get("id") == "feld")
        self.assertEqual({p["id"] for p in feld["parts"]} & {"feld", "referenz"}, {"feld", "referenz"})
        self.assertTrue(feld["cites"])
        off = {p["id"]: {"hidden": True} for p in feld["parts"]}
        b = bundle.build([self.r], {NAME: self.raw}, dict(self.req, styles={"feld": {"parts": off}}), lang="de")
        plain = next(i for i in b["items"] if i.get("id") == "feld")
        self.assertEqual(plain["cites"], [])
        self.assertNotIn(r"\cite", plain["caption"])
        self.assertNotIn("Vergleichsgruppe", plain["caption"])
        self.assertNotIn("Referenzwerkstoff", plain["caption"])
        self.assertIn("Vergleichsgruppe", plain["caption_full"])
        self.assertTrue(all(p.get("shown") is False for p in plain["parts"]))
        steps = json.loads(base64.b64decode(b["files"]["methods.json"]))["steps"]
        brief = next(s for s in steps if s["id"] == "kurz")
        text = base64.b64decode(b["files"][brief["file"]]).decode()
        self.assertEqual(len(split_sentences(text.strip())), 1, text)
        self.assertNotIn(r"\cite{mat-", text)

    def test_rebuild_keeps_slug(self):
        b = bundle.build([self.r], {NAME: self.raw}, {**self.req, "slug": "mein-ergebnis"}, lang="de")
        self.assertEqual(b["slug"], "mein-ergebnis")
        self.assertEqual(b["source"]["request"]["slug"], "mein-ergebnis")
        self.assertTrue(all(i.get("label", "fig:mein-ergebnis-").split(":")[1].startswith("mein-ergebnis-")
                            for i in b["items"] if "label" in i))


if __name__ == "__main__":
    unittest.main()
