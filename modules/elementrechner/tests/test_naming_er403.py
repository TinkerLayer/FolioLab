"""ER-403: Regelnamen für Heteromonocyclen, sekundäre/tertiäre Amine und N-substituierte Amide.

Sollwerte nach Favre & Powell 2014 (IUPAC-Empfehlungen 2013), von Hand geprüft:
- Heterocyclen: beibehaltene bzw. Hantzsch-Widman-Namen mit fester Bezifferung (P-22.2, P-25.2), Indikator-Wasserstoff
  im PIN (1H-pyrrole, P-31.1.4.2.4), Oxolan statt Tetrahydrofuran, 1,3-Thiazol/1,3-Oxazol mit Lokanten.
- Amine: substitutiv als N-substituierte Stammamine (P-62.2.1.1), Anilin als beibehaltener Name.
- Amide: N-Präfixe (P-66.1.1.4); formamide, acetamide und acetonitrile sind beibehaltene PINs (P-66.1.1.1.1,
  P-66.5.1.1.1), benzamide bleibt.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parents[1] / "sdk" / "python"))

from labcalc import molgraph as G  # noqa: E402
from labcalc import naming as N  # noqa: E402


class NamingER403(unittest.TestCase):
    HETEROCYCLES = {
        "c1ccncc1": "pyridine",
        "C1=CC=NC=C1": "pyridine",                         # Kekulé-Schreibweise
        "Cc1ccccn1": "2-methylpyridine",
        "Cc1ccncc1": "4-methylpyridine",
        "Clc1ccc(Cl)cn1": "2,5-dichloropyridine",
        "Oc1cccnc1": "pyridin-3-ol",
        "Nc1ccccn1": "pyridin-2-amine",
        "OC(=O)c1cccnc1": "pyridine-3-carboxylic acid",
        "NC(=O)c1cccnc1": "pyridine-3-carboxamide",
        "N#Cc1ccncc1": "pyridine-4-carbonitrile",
        "Clc1nc(Cl)c(Cl)c(Cl)c1Cl": "pentachloropyridine",   # P-14.3.4.3: voll substituiert, ohne Lokanten
        "c1ccoc1": "furan",
        "O=Cc1ccco1": "furan-2-carbaldehyde",
        "Cc1ccc(o1)C=O": "5-methylfuran-2-carbaldehyde",
        "c1ccsc1": "thiophene",
        "Brc1ccsc1": "3-bromothiophene",
        "OC(=O)c1cccs1": "thiophene-2-carboxylic acid",
        "c1cc[nH]c1": "1H-pyrrole",
        "Cn1cccc1": "1-methyl-1H-pyrrole",
        "OC(=O)c1ccc[nH]1": "1H-pyrrole-2-carboxylic acid",
        "c1c[nH]cn1": "1H-imidazole",
        "Cn1ccnc1": "1-methyl-1H-imidazole",
        "Cc1c[nH]cn1": "4-methyl-1H-imidazole",             # Tautomer aus dem SMILES: NH = 1
        "c1cn[nH]c1": "1H-pyrazole",
        "c1cocn1": "1,3-oxazole",
        "c1cscn1": "1,3-thiazole",
        "Cc1nccs1": "2-methyl-1,3-thiazole",
        "c1cncnc1": "pyrimidine",
        "Nc1ccncn1": "pyrimidin-4-amine",
        "c1cnccn1": "pyrazine",
        "c1ccnnc1": "pyridazine",
        "c1ccc(-c2ccccc2)nc1": "2-phenylpyridine",          # Heterocyclus vor Carbocyclus (P-44.2.1.2)
        "OCCc1ccccn1": "2-(pyridin-2-yl)ethan-1-ol",
        "C1CCNCC1": "piperidine",
        "CN1CCCCC1": "1-methylpiperidine",
        "OC1CCNCC1": "piperidin-4-ol",
        "C1CCNC1": "pyrrolidine",
        "C1COCCN1": "morpholine",
        "CN1CCOCC1": "4-methylmorpholine",
        "c1ccc(cc1)N1CCOCC1": "4-phenylmorpholine",
        "C1CNCCN1": "piperazine",
        "C1CCOC1": "oxolane",
        "C1CCOCC1": "oxane",
        "C1CCSC1": "thiolane",
        "C1COCCO1": "1,4-dioxane",
        "CC1CO1": "2-methyloxirane",
    }
    AMINES = {
        "CNC": "N-methylmethanamine",
        "CN(C)C": "N,N-dimethylmethanamine",
        "CCNCC": "N-ethylethanamine",
        "CCN(CC)CC": "N,N-diethylethanamine",
        "CCN(C)C": "N,N-dimethylethanamine",
        "CCCNC": "N-methylpropan-1-amine",
        "CCN(C)CCC": "N-ethyl-N-methylpropan-1-amine",
        "CNc1ccccc1": "N-methylaniline",
        "CN(C)c1ccccc1": "N,N-dimethylaniline",
        "CNC1CCCCC1": "N-methylcyclohexanamine",
        "c1ccc(Nc2ccccc2)cc1": "N-phenylaniline",
        "CC(C)NC(C)C": "N-(propan-2-yl)propan-2-amine",
        "Clc1ccc(NC)cc1": "4-chloro-N-methylaniline",
        "CN(C)c1ccccn1": "N,N-dimethylpyridin-2-amine",
        "CN(C)CCO": "2-(dimethylamino)ethan-1-ol",
        "CN(C)c1ccc(C(=O)O)cc1": "4-(dimethylamino)benzoic acid",
    }
    AMIDES = {
        "CC(N)=O": "acetamide",
        "NC=O": "formamide",
        "CC#N": "acetonitrile",
        "NC(=O)c1ccccc1": "benzamide",
        "CNC(C)=O": "N-methylacetamide",
        "CN(C)C(C)=O": "N,N-dimethylacetamide",
        "CNC=O": "N-methylformamide",
        "CN(C)C=O": "N,N-dimethylformamide",
        "CNC(=O)c1ccccc1": "N-methylbenzamide",
        "CN(C)C(=O)c1ccccc1": "N,N-dimethylbenzamide",
        "CC(=O)Nc1ccccc1": "N-phenylacetamide",
        "CCNC(=O)CC": "N-ethylpropanamide",
        "CNC(=O)c1cccnc1": "N-methylpyridine-3-carboxamide",
    }
    GERMAN = {
        "c1ccncc1": "Pyridin", "c1ccsc1": "Thiophen", "c1cc[nH]c1": "1H-Pyrrol", "c1cscn1": "1,3-Thiazol",
        "OC(=O)c1cccnc1": "Pyridin-3-carbonsäure", "O=Cc1ccco1": "Furan-2-carbaldehyd", "C1CCOC1": "Oxolan",
        "CN1CCOCC1": "4-Methylmorpholin", "CNC": "N-Methylmethanamin", "CN(C)c1ccccc1": "N,N-Dimethylanilin",
        "CNC(=O)c1ccccc1": "N-Methylbenzamid", "CN(C)CCO": "2-(Dimethylamino)ethan-1-ol",
        "CC(N)=O": "Acetamid", "NC=O": "Formamid", "CC#N": "Acetonitril", "CN(C)C=O": "N,N-Dimethylformamid",
        "CNC(C)=O": "N-Methylacetamid",
    }
    REFUSED = (
        "c1ccc2[nH]ccc2c1",          # Indol (kondensiert)
        "c1ccc2ncccc2c1",            # Chinolin (kondensiert)
        "c1ncncn1",                  # 1,3,5-Triazin (nicht in der Tabelle)
        "c1nn[nH]n1",                # Tetrazol
        "O=c1cccc[nH]1",             # Pyridin-2(1H)-on (exocyclisches =O)
        "C1COC=C1",                  # 2,3-Dihydrofuran (teilhydriert)
        "C1=CCN=C1",                 # 2H-Pyrrol (kein Pyrrol-Heteroatom)
        "c1ccc(-c2ccccn2)nc1",       # 2,2'-Bipyridin (Ringverband)
        "C[N+](C)(C)C",              # quartäres Ammonium
        "NC(N)=O",                   # Harnstoff
        "CC(=O)N1CCCCC1",            # Amid am Ring-N
        "CC(=O)NC(C)=O",             # Imid
        "CNCCN",                     # zwei Amino-N (N, N′)
        "CNNC",                      # Hydrazin
        "CCS",                       # Thiol
        "CCN(C)CCO",                 # [ethyl(methyl)amino]-Präfix
        "c1ccn[c]c1",                # Radikal
    )

    def _check(self, cases):
        for smi, want in cases.items():
            with self.subTest(smi=smi):
                r = N.name(smi)
                self.assertEqual(r.get("en"), want, r.get("refused"))

    def test_heterocycles(self):
        self._check(self.HETEROCYCLES)

    def test_amines(self):
        self._check(self.AMINES)

    def test_amides(self):
        self._check(self.AMIDES)

    def test_count(self):
        self.assertGreaterEqual(len(self.HETEROCYCLES) + len(self.AMINES) + len(self.AMIDES), 40)
        self.assertGreaterEqual(len(self.REFUSED), 6)

    def test_german(self):
        for smi, want in self.GERMAN.items():
            with self.subTest(smi=smi):
                self.assertEqual(N.name(smi).get("de"), want)

    def test_synonym_note(self):
        self.assertIn("Tetrahydrofuran", " ".join(N.name("C1CCOC1")["notes"]))
        self.assertIn("DMF", " ".join(N.name("CN(C)C=O")["notes"]))

    def test_no_systematic_amide_names(self):
        """Die beibehaltenen PINs ersetzen ethanamide, methanamide und ethanenitrile vollständig."""
        for smi in ("CC(N)=O", "NC=O", "CC#N", "CNC(C)=O", "CN(C)C=O"):
            with self.subTest(smi=smi):
                self.assertNotRegex(N.name(smi)["en"], r"ethan|methan")

    def test_refusals(self):
        for smi in self.REFUSED:
            with self.subTest(smi=smi):
                r = N.name(smi)
                self.assertNotIn("en", r)
                self.assertTrue(r.get("refused"))

    def test_aromatic_hydrogen_count(self):
        """Aromatisches s und n mit drei Bindungen tragen keinen impliziten Wasserstoff."""
        cnt = lambda s: G.hill(G.parse(s).element_counts())   # noqa: E731
        self.assertEqual(cnt("c1ccsc1"), "C4H4S")
        self.assertEqual(cnt("Cn1cccc1"), "C5H7N")
        self.assertEqual(cnt("c1cscn1"), "C3H3NS")


if __name__ == "__main__":
    unittest.main()
