"""Exports, material database, specimens, command line and server of the tensile module.

Tests that need a whole measurement use tests/_input.py (the synthetic curve of test_dataset.py, or a measurement
named in FOLIO_ZV_REFERENCE). Run:  python -m unittest discover -s tests -v
"""
import math
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from flps import alloys, analyse  # noqa: E402
from flps.parser import parse_bytes  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _input import measurement  # noqa: E402

def _measured():
    """A whole measurement (the outputs tested here do not depend on its values)."""
    raw, name, _real = measurement()
    return parse_bytes(raw, name)


class TestExports(unittest.TestCase):
    """Abschnitt 6: alle Ausgaben werden geschrieben, die Mappe hat keine Fehlerwerte."""

    def test_exports_with_reference_material(self):
        from flps.export import write_all
        cases = [analyse.Config(shape="ISO 527-2 Typ 5B", width_mm=2.0, thickness_mm=0.1, l0_mm=10.0,
                                speed_mm_min=1.0, displacement_source="traverse", material_ref="EN AW-5052-H38"),
                 analyse.Config(specimen_mode="manuell", section="rohr", outer_d_mm=3, wall_mm=0.05, l0_mm=10,
                                material_ref="S235JR", compare_group="alle Metalle"),
                 analyse.Config(material_ref="PA6 trocken")]
        for cfg in cases:
            r = analyse.run(_measured(), cfg)
            with tempfile.TemporaryDirectory() as d:
                names = {p.name for p in write_all(r, Path(d), overwrite=False)}
                for suffix in (".csv", ".xlsx", "_Datenblatt.pdf", "_Bildanhang.pdf", "_Bericht.pdf"):
                    self.assertTrue(any(n.endswith(suffix) for n in names), (suffix, cfg.material_ref))

    def test_all_exports(self):
        from flps.export import write_all
        cfg = analyse.Config(shape="ISO 527-2 Typ 5B", width_mm=2.0, thickness_mm=0.1, l0_mm=10.0,
                             speed_mm_min=1.0, displacement_source="traverse")
        r = analyse.run(_measured(), cfg)
        with tempfile.TemporaryDirectory() as d:
            out = write_all(r, Path(d), overwrite=False)
            names = {p.name for p in out}
            for suffix in (".csv", ".xlsx", "_Datenblatt.pdf", "_Bildanhang.pdf", "_Bericht.pdf"):
                self.assertTrue(any(n.endswith(suffix) for n in names), suffix)
            self.assertEqual(sum(n.endswith(".png") for n in names), 4)

    def test_report_variants_and_comparison(self):
        """Bericht ohne A0, mit Referenzwerkstoff anderer Klasse, Rohrprobe, Vergleichsbericht."""
        from flps.export import write_comparison
        from flps.export.report import write_report
        f = _measured()
        cfgs = [analyse.Config(),
                analyse.Config(material_ref="S235JR"),
                analyse.Config(specimen_mode="manuell", section="rohr", outer_d_mm=1.0, wall_mm=0.1, l0_mm=10,
                               speed_mm_min=1, material_ref="PA6 trocken")]
        rs = [analyse.run(f, c) for c in cfgs]
        with tempfile.TemporaryDirectory() as d:
            for r in rs:
                self.assertTrue(write_report(r, Path(d)).exists())
            a = analyse.run(f, analyse.Config(shape="ISO 527-2 Typ 5B", width_mm=2, thickness_mm=0.1, l0_mm=10, speed_mm_min=1))
            b = analyse.run(f, analyse.Config(shape="ISO 527-2 Typ 5B", width_mm=2, thickness_mm=0.12, l0_mm=10, speed_mm_min=1))
            p = write_comparison([a, b], Path(d))
            self.assertTrue(p.exists())
            with self.assertRaises(FileExistsError):
                write_comparison([a, b], Path(d))


class TestMaterialsAndSpecimens(unittest.TestCase):
    """Erweiterte Werkstoffdatenbank, Normproben, manuelle Abmessungen."""

    def test_database(self):
        al = alloys.load_alloys()
        cats = alloys.categories(al)
        for c in ("Stahl", "Aluminium", "Kunststoff", "Elastomer", "Folie", "Titan", "Kupfer"):
            self.assertIn(c, cats)
        self.assertGreater(len(al), 60)
        self.assertTrue(all(a.source for a in al), "jede Zeile braucht eine Quelle")
        self.assertEqual(len({a.name for a in al}), len(al), "Namen eindeutig")

    def test_shared_database_and_own_file(self):
        """The comparison materials come from the shared SDK database; --legierungen still reads a file."""
        import json
        from labcalc import materials
        rows = materials.zugversuch_rows()
        self.assertEqual([a.name for a in alloys.load_alloys()], [r["name"] for r in rows])
        self.assertEqual(materials.find("S235JR")["Rm_MPa"], alloys.find(alloys.load_alloys(), "S235JR").rm)
        keep = ("name", "Rp02_MPa", "Rm_MPa", "A_pct", "E_GPa", "quelle", "kategorie")
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "eigene.json"
            p.write_text(json.dumps({"werkstoffe": [{k: rows[0][k] for k in keep}]}), encoding="utf-8")
            own = alloys.load_alloys(p)
        self.assertEqual([a.name for a in own], [rows[0]["name"]])

    def test_default_group_is_aluminium(self):
        grp = alloys.select_group(alloys.load_alloys(), None)
        self.assertTrue(grp and all(a.category == "Aluminium" for a in grp))

    def test_ideal_curves_all_finite(self):
        import numpy as np
        for a in alloys.load_alloys():
            eps = np.linspace(0, a.a_pct / 100, 300)
            s = alloys.ideal_curve(a, eps)
            self.assertTrue(np.all(np.isfinite(s)), a.name)
            self.assertAlmostEqual(float(np.nanmax(s)), a.rm, delta=a.rm * 0.02, msg=a.name)

    def test_specimens(self):
        self.assertIn("ASTM D638 Type I", analyse.SHAPES)
        self.assertIn("DIN 50125 B 6×30", analyse.SHAPES)
        for legacy in ("ISO 527-2 Typ 1A", "ISO 527-2 Typ 1B", "ISO 527-2 Typ 5A", "ISO 527-2 Typ 5B",
                       "ISO 6892-1 Flachprobe", "Rundprobe", "Frei"):
            self.assertIn(legacy, analyse.SHAPES)
        self.assertEqual(analyse.SHAPES["ISO 527-2 Typ 5B"]["b"], 2.0)
        self.assertEqual(analyse.SHAPES["ISO 527-2 Typ 5B"]["L0"], 10.0)

    def test_tube_area(self):
        c = analyse.Config(section="rohr", outer_d_mm=10.0, wall_mm=1.0)
        self.assertAlmostEqual(c.area(), math.pi / 4 * (100 - 64), places=9)
        self.assertIsNone(analyse.Config(section="rohr", outer_d_mm=10.0, wall_mm=6.0).area())

    def test_reference_material_and_group(self):
        f = _measured()
        r = analyse.run(f, analyse.Config(width_mm=2, thickness_mm=0.1, material_ref="S235JR"))
        self.assertEqual(r.group, "Stahl")
        self.assertTrue(all(row["category"] == "Stahl" for row in r.comparison["rows"]))
        rm_ref = next(a.rm for a in alloys.load_alloys() if a.name == "S235JR")
        self.assertAlmostEqual(r.ref_cmp["d_rm_pct"], 100 * (r.kv["Rm"] - rm_ref) / rm_ref, places=6)
        r2 = analyse.run(f, analyse.Config(width_mm=2, thickness_mm=0.1, material_ref="S235JR",
                                           compare_group="alle Metalle"))
        self.assertGreater(len(r2.comparison["rows"]), 30)

    def test_norm_deviation_and_mismatch_notes(self):
        f = _measured()
        r = analyse.run(f, analyse.Config(shape="ISO 527-2 Typ 5B", width_mm=2.5, thickness_mm=0.1, l0_mm=10,
                                          material_ref="EN AW-6061-T6"))
        texts = " ".join(w["text"] for w in r.warnings)
        self.assertIn("weichen von der Normprobe", texts)
        self.assertIn("gedacht", texts)


class TestAlloyCurve(unittest.TestCase):
    def test_curve_shape(self):
        a = alloys.load_alloys()[0]
        import numpy as np
        eps = np.array([0.0, 0.3, 0.31])
        s = alloys.ideal_curve(a, eps)
        self.assertEqual(s[0], 0.0)
        self.assertAlmostEqual(s[1], a.rm * 0.93, places=6)
        self.assertTrue(math.isnan(s[2]))


class TestCliAndServer(unittest.TestCase):
    def _args(self, *argv):
        import argparse
        from flps import cli
        captured = {}
        orig = argparse.ArgumentParser.parse_args

        def grab(self_, args=None, namespace=None):
            ns = orig(self_, args, namespace)
            captured["ns"] = ns
            raise SystemExit(0)
        argparse.ArgumentParser.parse_args = grab
        try:
            with self.assertRaises(SystemExit):
                cli.main(list(argv))
        finally:
            argparse.ArgumentParser.parse_args = orig
        return cli.build_config(captured["ns"])

    def test_cli_norm_round(self):
        c = self._args("x.flps", "--form", "DIN 50125 B 6×30", "--werkstoff-ref", "S235JR")
        self.assertEqual((c.specimen_mode, c.section, c.diameter_mm, c.l0_mm), ("norm", "rund", 6.0, 30.0))
        self.assertEqual(c.material_ref, "S235JR")
        self.assertAlmostEqual(c.area(), math.pi * 9, places=6)

    def test_cli_manual_tube(self):
        c = self._args("x.flps", "--manuell", "--rohr", "10", "1", "--l0", "50", "--gruppe", "alle Metalle")
        self.assertEqual((c.specimen_mode, c.shape, c.section), ("manuell", analyse.MANUAL_SHAPE, "rohr"))
        self.assertAlmostEqual(c.area(), math.pi / 4 * (100 - 64), places=6)
        self.assertEqual(c.compare_group, "alle Metalle")

    def test_server_meta_and_envelope(self):
        from flps.ui import server
        server.STATE = server.State(Path(tempfile.mkdtemp()), None)
        m = server.meta_payload()
        self.assertIn("Stahl", m["categories"])
        self.assertIn("alle Werkstoffe", m["groups"])
        self.assertTrue(all("ratio" in a for a in m["alloys"]))
        env = server.envelope_payload("Stahl")
        names = {c["name"] for c in env["curves"]}
        self.assertIn("S235JR", names)
        self.assertNotIn("EN AW-6061-T6", names)

    def test_server_sketch(self):
        from flps.ui import server
        r = analyse.run(_measured(), analyse.Config(shape="ISO 527-2 Typ 5B", width_mm=2, thickness_mm=0.1))
        svg = server.sketch_svg(r)
        self.assertTrue(svg.startswith("<svg"))


if __name__ == "__main__":
    unittest.main()
