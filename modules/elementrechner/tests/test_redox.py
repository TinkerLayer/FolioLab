"""Tests Phase 5: Oxidationszahlen, Redox (Halbreaktionen, E°, Nernst, Faraday), Ionengleichung, Reaktionstyp,
pH, Titration, Puffer, Rechnerfunktionen und Berichtsteile.

Sollwerte:
- Oxidationszahlen nach IUPAC (Karen et al. 2016), von Hand: KMnO₄ Mn +7, Cr₂O₇²⁻ Cr +6, Fe₃O₄ Fe +8/3, H₂O₂ O −1,
  NaH H −1, OF₂ O +2; Essigsäure je Atom C −3 (CH₃) und +3 (COOH).
- Standardpotenziale (Lehrbuchwerte, Bard & Faulkner 2001 / Atkins 2018): Cu²⁺/Cu +0,34 V, Zn²⁺/Zn −0,76 V,
  Daniell-Element 1,10 V; MnO₄⁻/Mn²⁺ 1,51 V, Cl₂/Cl⁻ 1,36 V. Toleranz 0,01 V (berechnet aus ΔfG°).
- Nernst: E = 1,100 V − (RT/2F)·ln(1/0,01) = 1,041 V. Faraday: 2 A · 3600 s = 7200 C → 0,07462 mol e⁻.
- pH (Harris 2016, Rechenbeispiele): 0,1 M HCl 1,00; 0,1 M CH₃COOH 2,88; Acetatpuffer 1:1 4,76; 0,1 M NH₃ 11,12;
  0,1 M Na₂CO₃ 11,65. Titration 0,1 M Essigsäure (25 mL) mit 0,1 M NaOH: Äquivalenz 25,00 mL bei pH ≈ 8,7.
"""
from __future__ import annotations

import base64
import sys
import unittest
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parents[1] / "sdk" / "python"))

from labcalc import acidbase as AB  # noqa: E402
from labcalc import chem as C  # noqa: E402
from labcalc import expr as E  # noqa: E402
from labcalc import redox as RX  # noqa: E402

from elementrechner import analysis as A  # noqa: E402
from elementrechner import bundle as B  # noqa: E402
from laboptional import skip_unless  # noqa: E402


def mean_ox(formula, el):
    r = RX.formula_ox(C.parse_species(formula))
    pairs = r["atoms"][el]
    return sum(v * n for v, n in pairs) / sum(n for _, n in pairs)


def eq(text, **state):
    return A.run({"equation": text, **state})["equation"]


class Elements(unittest.TestCase):
    def test_data(self):
        els = RX._elements()
        self.assertEqual(len(els), 118)
        self.assertAlmostEqual(RX.en("F"), 3.98, places=2)
        self.assertIn(-2, RX.common_states("O"))
        self.assertTrue(RX.is_metal("Fe"))
        self.assertFalse(RX.is_metal("Cl"))


class OxidationNumbers(unittest.TestCase):
    def test_formula(self):
        self.assertEqual(mean_ox("KMnO4", "Mn"), 7)
        self.assertEqual(mean_ox("Cr2O7^2-", "Cr"), 6)
        self.assertEqual(mean_ox("Fe3O4", "Fe"), Fraction(8, 3))
        self.assertEqual(mean_ox("H2O2", "O"), -1)
        self.assertEqual(mean_ox("NaH", "H"), -1)
        self.assertEqual(mean_ox("OF2", "O"), 2)

    def test_structure(self):
        r = RX.structure_ox("CC(=O)O")
        self.assertEqual(sorted(v for v, _ in r["atoms"]["C"]), [-3, 3])
        self.assertEqual(RX.fstr(Fraction(8, 3)), "+8/3")
        self.assertEqual(RX.fstr(-2), "−2")

    def test_mixed_methods_no_false_redox(self):
        # CH₃COOH (Formel, Mittelwert) und CH₃COONa (Struktur, je Atom) dürfen keine Redoxreaktion vortäuschen
        r = eq("CH3COOH + NaOH -> CH3COONa + H2O")
        self.assertFalse(r["redox"]["redox"])
        self.assertEqual([t["key"] for t in r["rtype"]][0], "acidbase")


class Redox(unittest.TestCase):
    def test_half_reaction_potentials(self):
        for text, E0 in (("Cu^2+ + 2 e- -> Cu", 0.337), ("Zn^2+ + 2 e- -> Zn", -0.763),
                         ("MnO4^- + 8 H^+ + 5 e- -> Mn^2+ + 4 H2O", 1.51), ("Cl2 + 2 e- -> 2 Cl^-", 1.36)):
            r = eq(text)["redox"]
            self.assertTrue(r["half"], text)
            self.assertAlmostEqual(r["E_half"]["E0"], E0, delta=0.01, msg=text)
        self.assertEqual(eq("Cu^2+ + 2 e- -> Cu")["redox"]["couple"], "Cu²⁺/Cu")

    def test_daniell_from_salts(self):
        r = eq("Zn + CuSO4 -> ZnSO4 + Cu", redox={"activities": {"1": 0.01}, "faraday": {"I": 2, "t": 3600}})
        x = r["redox"]
        self.assertEqual(x["n"], 2)
        self.assertEqual(x["oxidized"], ["Zn"])
        self.assertEqual(x["reduced"], ["Cu"])
        self.assertEqual(x["halves"]["oxidation"]["unicode"], "Zn → Zn²⁺ + 2 e⁻")
        self.assertIn("Zn + Cu²⁺", x["halves"]["from_ionic"])
        self.assertAlmostEqual(x["potential"]["E0_cell"], 1.100, delta=0.01)
        self.assertAlmostEqual(x["nernst"]["E"], x["potential"]["E0_cell"] - 0.05916, delta=0.0005)
        self.assertAlmostEqual(x["faraday"]["Q"], 7200)
        self.assertAlmostEqual(x["faraday"]["n_e"], 0.074623, places=5)
        self.assertEqual([t["key"] for t in r["rtype"]], ["redox", "displacement"])
        self.assertEqual(x["faraday"]["warnings"], [])

    def test_faraday_efficiency_and_yield(self):
        full = eq("Zn + CuSO4 -> ZnSO4 + Cu", redox={"faraday": {"I": 2, "t": 3600}})["redox"]["faraday"]
        cu = next(w for w in full["rows"] if w["species"] == "Cu")
        self.assertAlmostEqual(cu["m_g"], 2.3709, places=3)              # 7200 C / (2 F) · 63,546 g/mol
        r = eq("Zn + CuSO4 -> ZnSO4 + Cu", redox={"faraday": {"I": 2, "t": 3600, "eta": 90, "actual": {"3": 2.0}}})
        fa = r["redox"]["faraday"]
        cu9 = next(w for w in fa["rows"] if w["species"] == "Cu")
        self.assertAlmostEqual(fa["eta"], 0.9)
        self.assertAlmostEqual(cu9["m_g"], 0.9 * cu["m_g"], places=6)
        self.assertAlmostEqual(cu9["yield"], 2.0 / cu["m_g"], places=6)    # Ausbeute gegen η = 100 %
        bad = eq("Zn + CuSO4 -> ZnSO4 + Cu", redox={"faraday": {"Q": 100, "eta": 120}})["redox"]["faraday"]
        self.assertIn("error", bad)
        tex = B.build({"state": {"equation": "Zn + CuSO4 -> ZnSO4 + Cu",
                                 "redox": {"faraday": {"I": 2, "t": 3600, "eta": 90, "actual": {"3": 2.0}}}}}, "de")
        keys = [v["key"] for it in tex["items"] if it["kind"] == "values" for v in it["values"]]
        self.assertIn("Y-el3", keys)

    def test_faraday_warns_on_several_couples(self):
        fa = eq("KMnO4 + HCl -> KCl + MnCl2 + Cl2 + H2O", redox={"faraday": {"Q": 1000}})["redox"]["faraday"]
        self.assertEqual(fa["warnings"], [])                               # ein Paar je Seite
        fa2 = eq("Cl2 + NaOH -> NaCl + NaClO + H2O", redox={"faraday": {"Q": 1000}})["redox"]["faraday"]
        self.assertTrue(any("Disproportionierung" in w or "Dis-" in w for w in fa2["warnings"]))

    def test_permanganate_hcl(self):
        x = eq("KMnO4 + HCl -> KCl + MnCl2 + H2O + Cl2")["redox"]
        self.assertEqual(x["n"], 10)
        self.assertAlmostEqual(x["halves"]["reduction"]["E0"], 1.51, delta=0.01)
        self.assertAlmostEqual(x["halves"]["oxidation"]["E0"], 1.36, delta=0.01)
        self.assertAlmostEqual(x["halves"]["E0_cell_halves"], 0.15, delta=0.01)

    def test_medium_balancing(self):
        r = eq("MnO4^- + Fe^2+ -> Mn^2+ + Fe^3+")
        self.assertEqual(r["status"], "impossible")
        opts = {o["medium"]: o["text"] for o in r["medium_options"]}
        self.assertEqual(opts["acid"], "MnO4^- + 5 Fe^2+ + 8 H^+ -> Mn^2+ + 5 Fe^3+ + 4 H2O")
        self.assertEqual(opts["base"], "MnO4^- + 5 Fe^2+ + 4 H2O -> Mn^2+ + 5 Fe^3+ + 8 OH^-")

    def test_dichromate(self):
        r = eq("K2Cr2O7 + FeSO4 + H2SO4 -> Cr2(SO4)3 + Fe2(SO4)3 + K2SO4 + H2O")
        self.assertEqual(r["ionic"]["text"], "Cr2O7^2- + 6 Fe^2+ + 14 H^+ -> 2 Cr^3+ + 6 Fe^3+ + 7 H2O")
        self.assertEqual(r["redox"]["halves"]["reduction"]["unicode"], "Cr₂O₇²⁻ + 6 e⁻ + 14 H⁺ → 2 Cr³⁺ + 7 H₂O")


class Ionic(unittest.TestCase):
    def test_net_ionic(self):
        cases = {
            "AgNO3 + NaCl -> AgCl + NaNO3": "Ag^+ + Cl^- -> AgCl",
            "HCl + NaOH -> NaCl + H2O": "H^+ + OH^- -> H2O",
            "BaCl2 + Na2SO4 -> BaSO4 + NaCl": "Ba^2+ + SO4^2- -> BaSO4",
            "Fe + HCl -> FeCl2 + H2": "Fe + 2 H^+ -> Fe^2+ + H2",
            "CH3COOH + NaOH -> CH3COONa + H2O": "CH3COOH + OH^- -> CH3COO^- + H2O",
            "Cu + HNO3 -> Cu(NO3)2 + NO + H2O": "3 Cu + 8 H^+ + 2 NO3^- -> 3 Cu^2+ + 2 NO + 4 H2O",
        }
        for q, want in cases.items():
            self.assertEqual(eq(q)["ionic"]["text"], want, q)
        self.assertNotIn("ionic", eq("C3H8 + O2 -> CO2 + H2O"))

    def test_solubility(self):
        from labcalc import substances as S
        self.assertTrue(S.sparingly_soluble("AgCl"))
        self.assertTrue(S.sparingly_soluble("BaSO4"))
        self.assertFalse(S.sparingly_soluble("NaCl"))
        self.assertFalse(S.sparingly_soluble("CuSO4"))


class ReactionType(unittest.TestCase):
    def test_types(self):
        keys = lambda q: [t["key"] for t in eq(q)["rtype"]]   # noqa: E731
        self.assertIn("precipitation", keys("AgNO3 + NaCl -> AgCl + NaNO3"))
        self.assertIn("acidbase", keys("HCl + NaOH -> NaCl + H2O"))
        self.assertIn("combustion", keys("C3H8 + O2 -> CO2 + H2O"))
        self.assertIn("disproportionation", keys("Cl2 + NaOH -> NaCl + NaClO + H2O"))
        self.assertIn("decomposition", keys("CaCO3 -> CaO + CO2"))
        self.assertEqual(keys("Cu^2+ + 2 e- -> Cu"), ["half"])


class AcidBase(unittest.TestCase):
    @skip_unless('srd46')
    def test_ph_values(self):
        for mix, want in (("0,1 M HCl", 1.00), ("0,1 M CH3COOH", 2.88), ("0,1 M CH3COOH; 0,1 M CH3COONa", 4.76),
                          ("0,1 M NH3", 11.12), ("0,1 M Na2CO3", 11.65), ("1e-8 M HCl", 6.98)):
            self.assertAlmostEqual(AB.ph(mix)["pH"], want, delta=0.015, msg=mix)

    def test_titration(self):
        t = AB.titration("0,1 M CH3COOH", 25, "NaOH", 0.1, 50)
        self.assertEqual(len(t["equivalence"]), 1)
        self.assertAlmostEqual(t["equivalence"][0]["V"], 25.0, delta=0.05)
        self.assertAlmostEqual(t["equivalence"][0]["pH"], 8.72, delta=0.1)

    @skip_unless('srd46')
    def test_buffer(self):
        b = AB.buffer("Essigsäure", 4.76, 0.1)
        self.assertEqual(b["k"], 1)
        self.assertAlmostEqual(b["ratio_base_acid"], 1.0, delta=0.05)
        self.assertTrue(b["in_range"])
        self.assertTrue(any(h["key"] == b["key"] for h in AB.buffer_suggestions(4.76, 40)))

    @skip_unless('srd46')
    def test_common_buffers_first(self):
        self.assertEqual(len(AB._common_keys()), len(AB.COMMON_BUFFERS))   # alle Laborpuffer haben NIST-Daten
        hits = AB.buffer_suggestions(7.4)
        flags = [h["common"] for h in hits]
        self.assertTrue(flags[0])
        self.assertEqual(flags, sorted(flags, reverse=True))             # übliche Puffer stehen vorn
        names = {h["name"] for h in hits[:5]}
        self.assertTrue({"HEPES", "Phosphorsäure"} <= names)

    def test_pkw_temperature(self):
        # Tabelle bei 0,1 MPa in Bandura & Lvov 2006
        for t, want in ((0, 14.946), (25, 13.995), (50, 13.264), (75, 12.696), (100, 12.252)):
            self.assertAlmostEqual(AB.pkw(t), want, delta=0.002, msg=t)
        self.assertAlmostEqual(AB.water_density(4), 999.97, delta=0.01)        # Dichtemaximum (Kell 1975)
        with self.assertRaises(AB.AcidBaseError):
            AB.pkw(120)
        r = AB.ph("1e-7 M NaCl", 50)
        self.assertAlmostEqual(r["pH"], 6.63, delta=0.01)                       # neutral bei 50 °C
        self.assertAlmostEqual(r["pH_neutral"], 13.264 / 2, delta=0.002)
        self.assertEqual(r["T_C"], 50)
        self.assertIn("kell1975", r["refs"])
        self.assertAlmostEqual(AB.ph("0,01 M NaOH", 50)["pH"], 13.264 - 2, delta=0.01)
        # pKa bei 25 °C gemessen -> Hinweis bei anderer Temperatur, keiner bei 25 °C
        self.assertTrue(any("Messtemperatur" in n for n in AB.ph("0,1 M CH3COOH", 50)["notes"]))
        self.assertFalse(any("Messtemperatur" in n for n in AB.ph("0,1 M CH3COOH")["notes"]))
        self.assertTrue(AB.buffer("Essigsäure", 4.76, 0.1, T_C=60)["notes"])
        t = AB.titration("0,1 M HCl", 20, "NaOH", 0.1, 40, n=81, T_C=50)
        self.assertAlmostEqual(t["equivalence"][0]["pH"], 13.264 / 2, delta=0.05)

    def test_parallel_cold_start(self):
        # Der Server ist mehrfädig: ein zweiter Thread darf während des Indexaufbaus keinen leeren Index sehen
        import threading
        from labcalc import substances as S
        S._index_build.cache_clear()
        res, errs = [], []

        def go():
            try:
                res.append(AB.ph("0,1 M CH3COOH"))
            except Exception as e:  # noqa: BLE001
                errs.append(e)
        ts = [threading.Thread(target=go) for _ in range(6)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        self.assertEqual(errs, [])
        for r in res:
            self.assertAlmostEqual(r["pH"], 2.88, delta=0.015)

    @skip_unless('srd46')
    def test_indicators(self):
        inds = AB.indicators()
        self.assertGreaterEqual(len(inds), 20)
        for i in inds:
            self.assertEqual(i["source"], "harris")
            for r in i["ranges"]:
                self.assertLess(r["low"], r["high"])
        col = {c["key"]: c for c in AB.indicator_colours(9.0)}
        self.assertEqual(col["phenolphthalein"]["state"], "Umschlag")
        self.assertEqual(col["methyl_orange"]["colour"], "gelb")
        self.assertEqual(col["thymol_blue"]["state"], "Umschlag")             # zweiter Bereich 8,0–9,6
        # schwache Säure mit starker Base: Phenolphthalein geeignet, Methylorange nicht
        t = AB.titration("0,1 M CH3COOH", 25, "NaOH", 0.1, 50, n=81)
        sug = {x["key"]: x for x in t["equivalence"][0]["indicators"]}
        self.assertEqual(sug["phenolphthalein"]["rating"], "geeignet")
        self.assertLess(abs(sug["phenolphthalein"]["error_pct"]), 0.2)
        self.assertNotIn("methyl_orange", sug)
        self.assertNotIn("methyl_red", sug)
        self.assertEqual(sug["phenolphthalein"]["change"], "farblos → rot")
        # schwache Base mit starker Säure: Methylrot, nicht Phenolphthalein
        t = AB.titration("0,1 M NH3", 25, "HCl", 0.1, 50, n=81)
        sug = {x["key"]: x for x in t["equivalence"][0]["indicators"]}
        self.assertIn("methyl_red", sug)
        self.assertNotIn("phenolphthalein", sug)
        self.assertEqual(sug["methyl_red"]["change"], "gelb → rot")

    @skip_unless('srd46')
    def test_run_state(self):
        out = A.run({"ph": {"mixture": "0,1 M NH4Cl"},
                     "titration": {"analyte": "0,1 M HCl", "V0": 20, "titrant": "NaOH", "c": 0.1, "Vmax": 40}})
        self.assertAlmostEqual(out["ph"]["pH"], 5.12, delta=0.02)
        self.assertAlmostEqual(out["titration"]["equivalence"][0]["V"], 20.0, delta=0.05)


class Calculator(unittest.TestCase):
    def test_functions(self):
        E._register_chem()
        f = lambda n, *a: E.STRFUNCS[n][0](None, *a)   # noqa: E731
        self.assertAlmostEqual(f("E0r", "Cu^2+ + 2 e- -> Cu"), 0.337, delta=0.005)
        self.assertEqual(f("ne", "Zn + Cu^2+ -> Zn^2+ + Cu"), 2)
        self.assertEqual(f("oxn", "KMnO4", "Mn"), 7)
        self.assertAlmostEqual(f("pH", "0,1 M HCl"), 1.0, delta=0.01)
        self.assertAlmostEqual(f("pH", "0,01 M NaOH", 50), 11.26, delta=0.01)        # °C
        self.assertAlmostEqual(f("pH", "0,01 M NaOH", 323.15), 11.26, delta=0.01)    # K (SI)


class Report(unittest.TestCase):
    def _tex(self, d):
        return {k: base64.b64decode(v).decode("utf-8") for k, v in d["files"].items() if k.endswith(".tex")}

    def test_redox_and_ph_sections(self):
        for lang in ("de", "en"):
            d = B.build({"state": {"equation": "Zn + CuSO4 -> ZnSO4 + Cu", "ph": {"mixture": "0,1 M CH3COOH"},
                                   "titration": {"analyte": "0,1 M CH3COOH", "V0": 25, "titrant": "NaOH", "c": 0.1,
                                                 "Vmax": 50}}}, lang)
            ids = {i.get("id") for i in d["items"]}
            self.assertTrue({"redox", "oxidationszahlen", "ph", "speziesverteilung", "titration"} <= ids)
            vals = {v["key"] for i in d["items"] if i.get("kind") == "values" for v in i["values"]}
            self.assertTrue({"E0-r", "n-e", "ph", "V-eq1"} <= vals)
            tex = self._tex(d)
            for name, t in tex.items():
                self.assertFalse([c for c in t if ord(c) > 255], f"{lang} {name}: Zeichen ausserhalb Latin-1")
                for bad in ("\\ce{", "\\tfrac", "\\boldsymbol", "\\text{"):   # Vorlage ohne mhchem und amsmath
                    self.assertNotIn(bad, t, f"{lang} {name}")
            self.assertIn("er-karen2016", tex["text-redox.tex"])
            self.assertIn(r"\mathrm{pH} = ", tex["text-ph.tex"])
            self.assertIn("Phenolphthalein", tex["text-titration.tex"])
            self.assertIn("er-harris", tex["text-titration.tex"])
        d = B.build({"state": {"ph": {"mixture": "0,01 M NaOH", "T": 50}}}, "de")
        t = self._tex(d)["text-ph.tex"]
        self.assertIn("50\\,\\textdegree C", t)
        self.assertIn("13{,}264", t) if "{,}" in t else self.assertIn("13,264", t)
        self.assertIn("er-kell1975", t)


if __name__ == "__main__":
    unittest.main()
