"""Eigene Werkstoffe (mit Quelle und optionaler Kurve), zusätzlich eingeblendete Werkstoffe und eigene Gleichungen:
Prüfung, Diagramm, Server-Endpunkte und Bericht für Folio (Zitat mit DOI, Neuaufbau nach dem Löschen)."""
import base64
import json
import math
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parents[1] / "sdk" / "python"))

import numpy as np  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _input import measurement  # noqa: E402
from flps import alloys, analyse, bundle  # noqa: E402
from flps.parser import parse_bytes  # noqa: E402

RAW, NAME, _REAL = measurement()          # Referenzmessung, sonst die synthetische Kurve
CITE = {"type": "article", "authors": "Muster, A.; Beispiel, B.", "title": "Zugversuche an Testlegierungen",
        "container": "Journal of Testing", "year": "2024", "volume": "12", "pages": "1-10", "doi": "10.1234/zug.5678"}
CURVE = "Dehnung %;Spannung MPa\n0;0\n0,5;35\n2;80\n10;120\n25;140\n40;130\n"


def own_item(**kw):
    d = {"name": "Testlegierung X", "rp": 70, "rm": 140, "a_pct": 40, "e_gpa": 7, "category": "Eigene Werkstoffe",
         "basis": "Mittelwert aus 5 Proben", "cite": CITE}
    d.update(kw)
    return d


class OwnMaterialTest(unittest.TestCase):
    def test_validation(self):
        with self.assertRaisesRegex(ValueError, "Rm fehlt"):
            alloys.own_from_dict({"name": "x", "a_pct": 5, "e_gpa": 1})
        with self.assertRaisesRegex(ValueError, "grösser als Rm"):
            alloys.own_from_dict(own_item(rp=200))
        with self.assertRaisesRegex(ValueError, "Name fehlt"):
            alloys.own_from_dict(own_item(name=" "))
        a = alloys.own_from_dict(own_item(rm="140,5"))
        self.assertEqual(a.rm, 140.5)
        self.assertTrue(a.own)
        self.assertIn("Muster", a.source)       # Freitext aus der strukturierten Quelle

    def test_curve_text_and_derived_values(self):
        c = alloys.parse_curve(CURVE)
        self.assertEqual(c[0], [0.0, 0.0])
        self.assertEqual(c[1], [0.5, 35.0])       # Dezimalkomma, Kopfzeile übersprungen
        a = alloys.own_from_dict({"name": "nur Kurve", "curve": CURVE, "source": "Diagramm aus Bild 3"})
        self.assertEqual((a.rm, a.a_pct), (140.0, 40.0))
        self.assertGreater(a.e_gpa, 0)
        s = alloys.ideal_curve(a, np.array([0.0, 0.01, 0.175, 0.40, 0.41]))
        self.assertAlmostEqual(s[1], 35 + (80 - 35) * 0.5 / 1.5, places=6)
        self.assertAlmostEqual(s[2], 120 + 20 * 7.5 / 15, places=6)
        self.assertAlmostEqual(s[3], 130.0)
        self.assertTrue(math.isnan(s[4]))
        with self.assertRaises(ValueError):
            alloys.parse_curve("0;0\n1;2")

    def test_merge_skips_builtin_names(self):
        base = alloys.load_alloys()
        al, errs = alloys.merge_own(base, [own_item(), own_item(name="S235JR")])
        self.assertEqual(len(al), len(base) + 1)
        self.assertTrue(any("S235JR" in e for e in errs))


class ExtrasAndEquationsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = RAW
        cls.f = parse_bytes(cls.raw, NAME)
        cls.al, _ = alloys.merge_own(alloys.load_alloys(), [own_item(), own_item(name="Kurvenwerkstoff", curve=CURVE)])

    def cfg(self, **kw):
        base = dict(shape="ISO 527-2 Typ 5B", width_mm=2, thickness_mm=0.1, l0_mm=10, speed_mm_min=1,
                    displacement_source="traverse", material_ref="EN AW-5052-H38",
                    extra_refs=["Testlegierung X", "Kurvenwerkstoff", "S235JR", "gibt es nicht"],
                    equations=[{"sym": "Rrel", "label": "Rm relativ zur Referenz", "expr": "Rm/Rm_ref*100", "unit": "%",
                                "digits": 3, "source": None},
                               {"sym": "Wv", "label": "Arbeit je Volumen", "expr": "Wbreak*1000/(A0*L0)", "unit": "J/cm3"},
                               {"sym": "bad", "expr": "Rm/0"}])
        base.update(kw)
        return analyse.Config.from_dict(base)

    def test_extras_and_variables(self):
        r = analyse.run(self.f, self.cfg(), self.al)
        self.assertEqual([a.name for a in r.extras], ["Testlegierung X", "Kurvenwerkstoff", "S235JR"])
        from flps.export import charts
        members = charts.field_members(r)
        self.assertEqual(members[-3:], r.extras)
        self.assertEqual(len(members), len(r.alloys) + 3)
        for k in ("Fmax", "Rm", "A0", "L0", "Wbreak", "Rm_ref", "E", "A"):
            self.assertIn(k, r.variables)
        eq = {e["sym"]: e for e in r.equations}
        self.assertAlmostEqual(eq["Rrel"]["value"], r.kv["Rm"] / r.reference.rm * 100, places=6)
        self.assertIsNotNone(eq["Wv"]["value"])
        self.assertIsNotNone(eq["bad"]["error"])
        # Arbeit bis zum Bruch: Trapez über F(x), x aus dem Traversenweg ab t0
        self.assertGreater(r.variables["Wbreak"]["value"], 0)
        d = analyse.result_to_dict(r, include_series=False)
        json.dumps(analyse._clean(d))
        self.assertEqual(d["extras"], ["Testlegierung X", "Kurvenwerkstoff", "S235JR"])

    def test_chart_and_bundle(self):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from flps.export import charts
        r = analyse.run(self.f, self.cfg(material_ref="Kurvenwerkstoff"), self.al)
        fig = charts.chart3(r)
        labels = [t.get_text() for t in fig.axes[0].get_legend().get_texts()]
        # Referenz aus "Eigene Werkstoffe" -> beide eigenen im Feld, S235JR zusätzlich eingeblendet
        self.assertEqual(r.group, "Eigene Werkstoffe")
        self.assertEqual([a.name for a in r.extras], ["S235JR"])
        self.assertTrue(any(s.endswith("S235JR (idealisiert)") for s in labels))
        self.assertTrue(any("Referenz Kurvenwerkstoff (Kurve aus Quelle)" in s for s in labels))
        plt.close(fig)
        b = bundle.build([r], {NAME: self.raw}, {"items": [{"name": NAME, "config": r.config.to_dict()}]}, lang="de")
        bib = base64.b64decode(b["files"]["refs.bib"]).decode("utf-8")
        self.assertIn("@article{mat-testlegierung-x", bib)
        self.assertIn("10.1234/zug.5678", bib)
        self.assertIn("Mittelwert aus 5 Proben", bib)
        feld = next(i for i in b["items"] if i["kind"] == "figure" and i["id"] == "feld")
        self.assertIn("Zusätzlich eingeblendet", feld["caption"])
        self.assertIn("mat-testlegierung-x", feld["cites"])
        vals = base64.b64decode(b["files"]["values.tex"]).decode("utf-8")
        self.assertIn("eq-Rrel", vals)
        self.assertNotIn("eq-bad", vals)
        text = base64.b64decode(b["files"]["text-methodik.tex"]).decode("utf-8")
        self.assertIn(r"\[", text)
        self.assertTrue(any(i["kind"] == "table" and i["id"] == "gleichungen" for i in b["items"]))


class ServerOwnTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from flps.ui import server
        cls.server = server
        cls.tmp = Path(tempfile.mkdtemp())
        server.STATE = server.State(cls.tmp, None)
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def call(self, path, body=None, raw=None):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data, method="POST" if data is not None else "GET")
        try:
            with urllib.request.urlopen(req) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            return json.loads(e.read() or b"{}") | {"_status": e.code}

    def test_flow(self):
        # Quellenformular wird ausgeliefert
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/labref.js") as r:
            self.assertIn(b"LabRef", r.read())
        # Werkstoff ohne Quelle -> abgelehnt; eingebauter Name -> abgelehnt
        j = self.call("/api/own/save", {"item": own_item(cite=None)})
        self.assertIn("Quelle fehlt", j["error"])
        j = self.call("/api/own/save", {"item": own_item(name="S235JR")})
        self.assertIn("gibt es schon", j["error"])
        j = self.call("/api/own/save", {"item": own_item(curve=CURVE)})
        self.assertNotIn("error", j)
        oid = j["item"]["id"]
        self.assertTrue((self.tmp / "eigene_werkstoffe.json").exists())
        self.assertIn("Eigene Werkstoffe", j["meta"]["groups"])
        self.assertTrue(any(a["name"] == "Testlegierung X" and a["own"] for a in j["meta"]["alloys"]))
        env = self.call("/api/envelope?group=Eigene%20Werkstoffe")
        self.assertEqual(env["curves"][0]["name"], "Testlegierung X")
        # Gleichung speichern
        j = self.call("/api/equations/save", {"item": {"sym": "Rrel", "expr": "Rm/Rm_ref*100", "unit": "%",
                                                        "source": {"type": "book", "title": "Werkstoffprüfung", "authors": "Muster, A.", "year": "2020"}}})
        self.assertNotIn("error", j)
        eqs = j["items"]
        # Messung laden und auswerten, Referenz = eigener Werkstoff, zusätzlich S235JR
        j = self.call(f"/api/load?name={urllib.parse.quote(NAME)}", raw=RAW)
        fid = j["id"]
        cfg = dict(shape="ISO 527-2 Typ 5B", width_mm=2, thickness_mm=0.1, l0_mm=10, speed_mm_min=1,
                   displacement_source="traverse", material_ref="Testlegierung X", extra_refs=["S235JR"], equations=eqs)
        d = self.call("/api/analyse", {"id": fid, "config": cfg})
        self.assertEqual(d["group"], "Eigene Werkstoffe")
        self.assertEqual(d["equations"][0]["sym"], "Rrel")
        self.assertEqual([c["name"] for c in d["field_extra"]], ["S235JR"])
        self.assertEqual(d["field_extra"][0]["nr"], 2)
        b = self.call("/api/bundle", {"items": [{"id": fid, "config": cfg}], "lang": "de"})
        self.assertEqual([x["name"] for x in b["source"]["request"]["own_materials"]], ["Testlegierung X"])
        # Werkstoff löschen: der Bericht lässt sich trotzdem neu aufbauen, mit derselben Quelle
        self.call("/api/own/delete", {"id": oid})
        self.assertFalse(any(a.own for a in self.server.STATE.alloys))
        b2 = self.call("/api/bundle/rebuild", {"source": b["source"], "lang": "de"})
        self.assertNotIn("error", b2)
        bib = base64.b64decode(b2["files"]["refs.bib"]).decode("utf-8")
        self.assertIn("10.1234/zug.5678", bib)
        self.assertIn("Werkstoffprüfung", bib)     # Quelle der Gleichung
        # the hub's editing window: styles and describe_figures reach labbundle on a rebuild
        src = {**b["source"], "request": {**b["source"]["request"], "describe_figures": True,
                                          "styles": {"verlauf": {"title": "Neu"}}}}
        b3 = self.call("/api/bundle/rebuild", {"source": src, "lang": "de"})
        fig = next(i for i in b3["items"] if i.get("id") == "verlauf")
        self.assertIn("elements", fig.get("describe") or {})
        self.assertIn("axes", fig["describe"].get("now") or {})
        self.assertEqual((fig.get("style") or {}).get("title"), "Neu")
        # Export / Import
        ex = self.call("/api/own/export", {})
        self.assertEqual(json.loads(ex["text"])["items"], [])
        im = self.call("/api/own/import", {"data": {"items": [own_item(), own_item(name="S235JR"), {"name": "kaputt"}]}})
        self.assertEqual(im["added"], 1)
        self.assertEqual(len(im["skipped"]), 2)


if __name__ == "__main__":
    unittest.main()
