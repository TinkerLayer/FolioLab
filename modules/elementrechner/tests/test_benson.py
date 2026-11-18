"""Tests der Benson-Gruppenadditivität (ER-404).

Gruppenwerte: Domalski & Hearing, J. Phys. Chem. Ref. Data 22 (1993) 805, Table 2 (S. 816-819).
Sollwerte:
- Nachrechnung: die Spalte „Calculated“ derselben Arbeit (Tables 4-21) muss exakt (±0,015) herauskommen; damit ist die
  Übertragung jeder Gruppe geprüft.
- Vergleich mit Messwerten: Gasphasenwerte der Thermochemie-Sammlung (data/thermo.json, Burcat/Ruscic-Datenbank,
  Stand 2018, ΔfH° überwiegend ATcT). Toleranz nach Domalski & Hearing S. 809: Abweichungen bis ±4 kJ/mol (ΔfH°)
  bzw. ±4 J/(mol·K) (S°, Cp°) gelten als „sehr zufriedenstellend“. Verbindungen, bei denen schon D&H mehr als
  ±4 abweichen oder die Burcat-Entropie stark von der D&H-Literatur abweicht (Dimethylether, Neopentan,
  Methylacetat), sind für S° ausgenommen.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parents[1] / "sdk" / "python"))

from labcalc import benson as B  # noqa: E402
from labcalc import molgraph as G  # noqa: E402
from labcalc import thermo as TH  # noqa: E402
from laboptional import skip_unless  # noqa: E402


def est(smi):
    return B.estimate(G.parse(smi))


def burcat(key, name=None):
    """Gasphasen-Eintrag der Burcat-Datenbank zur InChIKey (bei Mehrdeutigkeit nach Namen)."""
    cand = [e for e in TH.data()["species"] if e.get("key") == key and e["ph"] == "g" and e["src"] == "burcat"]
    if name:
        cand = [e for e in cand if e.get("name", "") == name or e.get("name", "").endswith(" " + name)]
    assert len(cand) == 1, (key, name, len(cand))
    return cand[0]


# Name, SMILES, InChIKey, Burcat-Name, S° prüfen?
MOLS = [
    ("Propan", "CCC", "ATUOYWHBWRKTHZ-UHFFFAOYSA-N", None, True),
    ("n-Butan", "CCCC", "IJDNQMDRQITEOD-UHFFFAOYSA-N", None, True),
    ("Isobutan", "CC(C)C", "NNPPMTNAJDCUHE-UHFFFAOYSA-N", None, True),
    ("Neopentan", "CC(C)(C)C", "CRSOQBOWXPBRES-UHFFFAOYSA-N", None, False),
    ("Ethen", "C=C", "VGGSQFUCUMXWEO-UHFFFAOYSA-N", "C2H4", True),
    ("Propen", "C=CC", "QQONPFPTGQHPMA-UHFFFAOYSA-N", None, True),
    ("1-Buten", "C=CCC", "VXNZUUAINFGPBY-UHFFFAOYSA-N", None, True),
    ("Benzol", "c1ccccc1", "UHOVQNZJYSORNB-UHFFFAOYSA-N", "C6H6", True),
    ("Toluol", "Cc1ccccc1", "YXFVVABEGXRONW-UHFFFAOYSA-N", "TOLUENE", True),
    ("Ethanol", "CCO", "LFQSCWFLJHTTHZ-UHFFFAOYSA-N", None, True),
    ("1-Propanol", "CCCO", "BDERNNFJNOPAEC-UHFFFAOYSA-N", None, True),
    ("Dimethylether", "COC", "LCGLNKUTAGEVQW-UHFFFAOYSA-N", None, False),
    ("Ethanal", "CC=O", "IKHGUXGNUITLKF-UHFFFAOYSA-N", None, True),
    ("Aceton", "CC(C)=O", "CSCPPACGZOOCGX-UHFFFAOYSA-N", None, True),
    ("Butanon", "CCC(C)=O", "ZWEHNKRNPOVVGH-UHFFFAOYSA-N", None, True),
    ("Essigsäure", "CC(=O)O", "QTBSBXVTEAMEQO-UHFFFAOYSA-N", None, True),
    ("Methylacetat", "COC(C)=O", "KXKVLQRXCPHEJC-UHFFFAOYSA-N", None, False),
    ("Phenol", "Oc1ccccc1", "ISWSIDIOOBJBQZ-UHFFFAOYSA-N", None, True),
]

# D&H „Calculated“ (ΔfH°, Cp°, S°) und σ, aus den Verbindungstabellen
DH_CALC = [
    ("CC(C)C", -134.73, 97.27, 291.82, 81),           # Table 5, S. 835
    ("CC(C)(C)C", -168.08, 119.45, 302.59, 972),      # Table 6, S. 842
    ("CC(C)CC(C)(C)C", -222.90, 188.15, 417.86, 729),  # Table 6, S. 844 (tert/quat)
    ("C=C(C)C", -18.58, 87.94, 295.29, 18),           # Table 8, S. 852
    ("C=C/C=C\\C", 81.79, 94.90, 327.30, 3),          # Table 7, S. 850 (cis-Korrektur)
    ("Cc1ccccc1C", 19.26, 131.80, 350.13, 18),        # Table 10, S. 863 (ortho)
    ("CC(C)c1ccccc1", -0.87, 151.71, 388.55, 18),     # Table 11, S. 872
    ("C=C(C)c1ccccc1", 112.97, 145.18, 383.67, 6),    # Table 11, S. 874
    ("CCC(C)O", -292.84, 112.47, 359.74, 9),          # Table 15, S. 915 (η = 2)
    ("CC(C)(C)O", -313.29, 111.08, 322.32, 81),       # Table 15, S. 916
    ("COC(C)(C)C", -274.64, 136.06, 351.02, 243),     # Table 16, S. 928
    ("CC(C)OC(C)C", -318.42, 157.02, 390.71, 162),    # Table 16, S. 928
    ("CCC=O", -188.49, 79.42, 304.80, 3),             # Table 17, S. 935
    ("COC=O", -355.52, 66.53, 301.25, 3),             # Table 21, S. 966
    ("Cc1ccccc1O", -127.17, 130.34, 351.10, 3),       # Table 15, S. 921
]


class Reproduce(unittest.TestCase):
    def test_dh_calculated_values(self):
        for smi, H, Cp, S, sig in DH_CALC:
            r = est(smi)
            v = r["values"]
            self.assertAlmostEqual(v["dfH_g"]["v"], H, delta=0.015, msg=smi)
            self.assertAlmostEqual(v["Cp_g"]["v"], Cp, delta=0.015, msg=smi)
            self.assertAlmostEqual(v["S_g"]["v"], S, delta=0.015, msg=smi)
            self.assertEqual(r["sigma"], sig, smi)

    def test_every_group_sourced(self):
        t = B.table()
        for g in list(t["groups"].values()) + list(t["corr"].values()):
            self.assertEqual(g["src"], "domalski1993")
            self.assertIn(g["page"], (816, 817, 818, 819))
            self.assertTrue(g.get("check"), g["label"])
        self.assertIn("domalski1993", t["meta"]["sources"])


@skip_unless('burcat')
class Accuracy(unittest.TestCase):
    def test_against_tabulated(self):
        for name, smi, key, bname, check_s in MOLS:
            ref = burcat(key, bname)
            v = est(smi)["values"]
            self.assertAlmostEqual(v["dfH_g"]["v"], ref["H"], delta=4.0, msg=name)        # D&H S. 809: ±4 kJ/mol
            if check_s:
                self.assertAlmostEqual(v["S_g"]["v"], ref["S"], delta=4.0, msg=name)      # D&H S. 809: ±4 J/(mol·K)

    def test_heat_capacity(self):
        for name, smi, key, bname, _ in MOLS[:10]:
            ref = burcat(key, bname)
            self.assertAlmostEqual(est(smi)["values"]["Cp_g"]["v"], ref["Cp"], delta=4.0, msg=name)


class Labels(unittest.TestCase):
    def test_labelled_benson(self):
        r = est("CCO")
        self.assertEqual(r["method"], "Benson")
        self.assertIn("Domalski", r["method_long"])
        self.assertEqual(r["refs"], ["domalski1993", "benson1969"])
        for k in ("dfH_g", "S_g", "Cp_g"):
            self.assertIn("Benson", r["values"][k]["label"])
            self.assertEqual(r["values"][k]["method"], "Benson")
        self.assertTrue(any("Benson" in n for n in r["notes"]))
        self.assertEqual({g["group"] for g in r["groups"]}, {"C-(H)3(C)", "C-(H)2(O)(C)", "O-(H)(C)"})
        self.assertTrue(all("Domalski & Hearing 1993" in g["source"] for g in r["groups"]))
        self.assertIsNone(r["cp_poly"])                          # Quelle nur 298,15 K

    def test_cis_and_unspecified(self):
        trans, cis, unk = est("C/C=C/C"), est("C/C=C\\C"), est("CC=CC")
        self.assertAlmostEqual(cis["values"]["dfH_g"]["v"] - trans["values"]["dfH_g"]["v"], 4.85, places=6)
        self.assertEqual(unk["values"]["dfH_g"]["v"], trans["values"]["dfH_g"]["v"])
        self.assertTrue(any("E/Z" in n for n in unk["notes"]))

    def test_partial_values(self):
        r = est("CC(C)C=O")                                      # C-(H)(CO)(C)2: nur ΔfH° übernommen
        self.assertAlmostEqual(r["values"]["dfH_g"]["v"], -213.68, delta=0.015)
        self.assertIsNone(r["values"]["S_g"]["v"])
        self.assertIn("C-(H)(CO)(C)2", r["values"]["S_g"]["note"])


class Refusal(unittest.TestCase):
    def test_missing_group(self):
        with self.assertRaises(B.BensonError) as cm:
            est("OCc1ccccc1")                                    # Benzylalkohol: C-(H)2(O)(CB) nicht übernommen
        self.assertIn("Benson nicht anwendbar: Gruppe C-(H)2(CB)(O) fehlt", str(cm.exception))
        for smi in ("CCN", "C1CCCCC1", "c1ccc2ccccc2c1", "C", "C=C=C", "CCCl"):
            with self.assertRaises(B.BensonError, msg=smi):
                est(smi)

    def test_design_integration(self):
        from elementrechner import design as D
        r = D.analyze("CC(C)=O")
        self.assertIn("joback", r)                               # Joback bleibt als Rückfall
        self.assertEqual(r["benson"]["method"], "Benson")
        self.assertAlmostEqual(r["benson"]["values"]["dfH_g"]["v"], -217.19, delta=0.015)
        self.assertIn("domalski1993", r["refs"])
        r = D.analyze("CC(=O)N")
        self.assertIn("error", r["benson"])
        self.assertEqual(r["benson"]["method"], "Benson")
        self.assertNotIn("error", r["joback"])


if __name__ == "__main__":
    unittest.main()
