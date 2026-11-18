"""Gase (ER-L07)."""
import unittest

from labcalc import gas as G


class Gas(unittest.TestCase):
    def test_molar_volume(self):
        self.assertAlmostEqual(G.molar_volume(0, 100)["Vm_L_mol"], 22.711, delta=0.001)          # IUPAC-STP
        self.assertAlmostEqual(G.molar_volume(0, 1, p_unit="atm")["Vm_L_mol"], 22.414, delta=0.001)
        self.assertAlmostEqual(G.molar_volume(25, 1, p_unit="atm")["Vm_L_mol"], 24.465, delta=0.001)

    def test_ideal_any_unknown(self):
        r = G.ideal(p=101.325, V=None, n=1, T=0)
        self.assertEqual(r["solved"], "V")
        self.assertAlmostEqual(r["value"], 22.414, delta=0.001)
        self.assertAlmostEqual(G.ideal(p=None, V=22.414, n=1, T=0)["value"], 101.325, delta=0.01)
        self.assertAlmostEqual(G.ideal(p=1, V=24.465, n=None, T=25, p_unit="atm")["value"], 1.0, delta=1e-4)
        self.assertAlmostEqual(G.ideal(p=1, V=22.414, n=1, T=None, p_unit="atm", T_unit="K")["value"], 273.15,
                               delta=0.02)
        for bad in (lambda: G.ideal(p=1, V=1, n=1, T=1), lambda: G.ideal(p=None, V=None, n=1, T=1),
                    lambda: G.ideal(p=1, V=None, n=1, T=-300), lambda: G.ideal(p=1, V=None, n=1, T=0, p_unit="ft")):
            with self.assertRaises(G.GasError):
                bad()

    def test_density_and_mass(self):
        self.assertAlmostEqual(G.density("N2", 0, 1, p_unit="atm")["rho_g_L"], 1.2498, delta=0.0005)
        r = G.mass_to_volume("CO2", 44.0095, 0, 1, p_unit="atm")
        self.assertAlmostEqual(r["V_L"], 22.414, delta=0.002)
        self.assertAlmostEqual(r["n_mol"], 1.0, delta=1e-4)

    def test_dalton(self):
        r = G.mixture({"N2": 78.08, "O2": 20.95, "Ar": 0.93, "CO2": 0.04}, 101.325, basis="x")
        self.assertAlmostEqual(sum(c["x"] for c in r["components"].values()), 1.0, places=12)
        self.assertAlmostEqual(r["components"]["O2"]["p"], 0.2095 * 101.325, delta=0.01)
        with self.assertRaises(G.GasError):
            G.mixture({"A": -1, "B": 2}, 100)


if __name__ == "__main__":
    unittest.main()
