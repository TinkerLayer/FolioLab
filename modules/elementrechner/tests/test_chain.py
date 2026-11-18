"""UI-12: Reaktionsketten (Netz), Gesamtgleichung, Hess, Mengen vorwärts und rückwärts, grüne Kennzahlen."""
from __future__ import annotations

import sys
import unittest
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from elementrechner import analysis as AN  # noqa: E402
from elementrechner import chain as CH  # noqa: E402
from labcalc import chem as C  # noqa: E402

LIME = [{"id": "s1", "equation": "CaCO3(s) -> CaO(s) + CO2(g)", "yield": 90},
        {"id": "s2", "equation": "CaO(s) + H2O(l) -> Ca(OH)2(s)", "yield": 80}]


class ChainTest(unittest.TestCase):
    def test_linear_overall_and_links(self):
        r = CH.analyse(LIME)
        self.assertEqual(r["steps"][1]["links"][0]["from"], "s1")            # CaO automatisch aus Schritt 1
        self.assertIsNone(r["steps"][1]["links"][1]["from"])                   # Wasser ist Einsatzstoff
        self.assertEqual(r["overall"]["text"], "CaCO₃(s) + H₂O(l) → CO₂(g) + Ca(OH)₂(s)")   # Phasen bleiben (Hess)
        self.assertEqual(r["overall"]["intermediates"], ["CaO(s)"])

    def test_hess_equals_direct_overall(self):
        r = CH.analyse(LIME)
        eq = C.parse_equation("CaCO3(s) + H2O(l) -> CO2(g) + Ca(OH)2(s)")
        direct = AN.thermo_result(eq, [Fraction(1)] * 4)
        self.assertAlmostEqual(r["hess"]["dH"], direct["dH"], places=6)
        self.assertAlmostEqual(r["hess"]["dG"], direct["dG"], places=6)
        self.assertEqual(r["hess"]["missing"], [])

    def test_forward_amounts_and_overall_yield(self):
        r = CH.analyse(LIME, {"s1|CaCO3": {"value": 100.0869, "unit": "g"}})
        a = r["amounts"]
        self.assertEqual(a["mode"], "forward")
        self.assertAlmostEqual(a["product"]["n_theor"], 1.0, places=4)
        self.assertAlmostEqual(a["product"]["n_actual"], 0.72, places=4)
        self.assertAlmostEqual(a["yield_overall"], 72.0, places=6)
        self.assertEqual(r["steps"][1]["limiting"], "CaO")                     # Wasser ohne Menge: Überschuss

    def test_target_mode(self):
        r = CH.analyse(LIME, target={"step": "s2", "species": "Ca(OH)2", "value": 1, "unit": "mol"})
        feed = {f["species"]: f for f in r["amounts"]["feeds"]}
        self.assertAlmostEqual(feed["CaCO3"]["n"], 1 / (0.9 * 0.8), places=6)
        self.assertAlmostEqual(feed["H2O"]["n"], 1 / 0.8, places=6)
        self.assertAlmostEqual(r["amounts"]["yield_overall"], 72.0, places=6)
        g = r["green"]                                                          # Massen aller Einsatzstoffe bekannt
        self.assertAlmostEqual(g["PMI"], (feed["CaCO3"]["m"] + feed["H2O"]["m"]) / r["amounts"]["product"]["m_actual"], places=9)
        self.assertAlmostEqual(g["AE"], 100 * 74.0927 / (100.0869 + 18.0153), places=2)

    def test_branch_and_merge_with_surplus(self):
        steps = [{"id": "a", "equation": "CH4 + 2 H2O -> CO2 + 4 H2"},
                 {"id": "b", "equation": "N2 + 3 H2 -> 2 NH3"},
                 {"id": "c", "equation": "CO2 + 2 NH3 -> CO(NH2)2 + H2O"}]
        r = CH.analyse(steps, with_thermo=False)
        self.assertEqual([l["from"] for l in r["steps"][2]["links"]], ["a", "b"])   # zwei Quellen fliessen zusammen
        self.assertEqual(r["overall"]["text"], "CH₄ + H₂O + N₂ → H₂ + CO(NH₂)₂")   # Reihenfolge des ersten Auftretens
        self.assertEqual(r["overall"]["surplus"], ["H₂"])

    def test_link_override_and_bad_reference(self):
        steps = [dict(LIME[0]), {**LIME[1], "links": {"CaO": "feed"}}]
        r = CH.analyse(steps, with_thermo=False)
        self.assertIsNone(r["steps"][1]["links"][0]["from"])                   # CaO als Einsatzstoff erzwungen
        self.assertEqual(r["steps"][0]["mult"], "1")                           # Schritt 1 speist nichts mehr
        r2 = CH.analyse([dict(LIME[0]), {**LIME[1], "links": {"CaO": "zz"}}], with_thermo=False)
        self.assertTrue(any("zz" in n for n in r2["notes"]))

    def test_errors_and_limits(self):
        r = CH.analyse([{"id": "x", "equation": "H2 + O2 -> H2O"}, {"id": "y", "equation": "Fe + O2 -> NaCl"}], with_thermo=False)
        self.assertTrue(r["steps"][0]["ok"])
        self.assertFalse(r["steps"][1]["ok"])
        with self.assertRaises(C.ChemError):
            CH.analyse([{"id": "s", "equation": "H2 -> H2"}] * (CH.MAX_STEPS + 1))
        with self.assertRaises(C.ChemError):
            CH.analyse([{"id": "s", "equation": "H2 + O2 -> H2O"}] * 2)


class ReportTest(unittest.TestCase):
    def _tex(self, d, name):
        import base64
        return base64.b64decode(d["files"][name]).decode("utf-8")

    def test_chain_and_values_in_report(self):
        from elementrechner import bundle as B
        state = {"chain": {"steps": LIME, "feeds": {"s1|CaCO3": {"value": 100.0869, "unit": "g"}}},
                 "values": [{"sym": "pKa_HAc", "label": "pKₐ Essigsäure – ΔfH° egal", "value": "4,756", "unit": "",
                             "source": {"short": "SRD 46", "text": "NIST SRD 46 „Critically Selected Stability Constants“"},
                             "copied": "2026-11-17T15:02:11",
                             "used": [{"where": "pH: Lösung", "at": "2026-11-17T15:03:00"}, {"where": "pH: Lösung"}]}]}
        d = B.build({"state": state}, lang="de")
        names = [n for n in d["files"] if n.endswith(".tex")]
        self.assertIn("text-reaktionskette.tex", names)
        self.assertIn("kette-schritte.tex", names)
        self.assertIn("uebernommene-werte.tex", names)
        for n in names:
            t = self._tex(d, n)
            t.encode("latin-1")                                               # LaTeX-Regel: nur Latin-1
            for bad in ("\\text{", "\\ce{", "\\tfrac", "\\boldsymbol"):
                self.assertNotIn(bad, t)
        vt = self._tex(d, "uebernommene-werte.tex")
        self.assertIn("SRD 46", vt)
        self.assertEqual(vt.count("pH: L"), 1)                              # eingesetzt in: ohne Doppelte
        txt = self._tex(d, "text-reaktionskette.tex")
        self.assertIn("Hess", txt)
        self.assertIn("72", txt)                                             # Gesamtausbeute 72 %
        keys = [v[0] if isinstance(v, (list, tuple)) else v.get("key") for v in (d.get("values") or [])]
        self.assertTrue(any("kette" in str(k) for k in keys) or "kette-dh" in str(d))

    def test_single_step_chain_is_ignored(self):
        from elementrechner import bundle as B
        d = B.build({"state": {"equation": "H2 + O2 -> H2O", "chain": {"steps": LIME[:1]}}}, lang="en")
        self.assertNotIn("text-reaktionskette.tex", d["files"])


if __name__ == "__main__":
    unittest.main()
