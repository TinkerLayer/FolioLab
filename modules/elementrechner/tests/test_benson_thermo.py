"""ER-404: Benson-Schätzwerte eigener Stoffe in der Thermochemie – Vorrang vor Joback, nach Tabellenwerten."""
import unittest
from unittest import mock

from labcalc import chem as C
from labcalc import substances as S
from labcalc import thermo as T

BEN = "Benson-Gruppenadditivität (Domalski & Hearing 1993)"


def _own(formula, values):
    return {"own-x": {"name": "Testmolekül", "formula": formula, "values": values}}


def _v(v, method, unit="kJ/mol"):
    return [{"v": v, "u": unit, "est": True, "phase": "g", "method": method}]


class BensonPriority(unittest.TestCase):
    def test_source_keys(self):
        self.assertLess(T.PRIO["estb"], T.PRIO["est"])
        self.assertGreater(T.PRIO["estb"], T.PRIO["burcat"])
        self.assertEqual(T.SRC_REFS["estb"], ["domalski1993", "benson1969"])
        self.assertIn("Benson", T.SRC_NAME["estb"])

    def test_benson_preferred_over_joback(self):
        values = {"dfH": _v(-300.0, "Joback & Reid 1987") + _v(-310.0, BEN),
                  "dfG": _v(-150.0, "Joback & Reid 1987"),
                  "S0": _v(400.0, BEN, "J/(mol·K)")}
        with mock.patch.object(S, "_user", return_value=_own("C7H16O4", values)):
            ents = T._own_entries(C.parse_species("C7H16O4"))
        srcs = {e["src"]: e for e in ents}
        self.assertEqual(set(srcs), {"est", "estb"})
        best = T._best(ents)
        self.assertEqual(best["src"], "estb")
        self.assertEqual(best["H"], -310.0)
        self.assertIsNotNone(best.get("G"))                    # aus ΔfH° und S° berechnet

    def test_table_value_beats_benson(self):
        sp = C.parse_species("C2H6O")                          # Ethanol hat Tabellenwerte
        with mock.patch.object(S, "_user", return_value=_own("C2H6O", {"dfH": _v(-200.0, BEN),
                                                                      "S0": _v(280.0, BEN, "J/(mol·K)")})):
            best = T._best(T.candidates(sp))
        self.assertNotIn(best["src"], ("est", "estb"))


if __name__ == "__main__":
    unittest.main()
