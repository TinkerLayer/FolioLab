"""Werkstoffe-Modul: Kristallographie, XRD-Leser und -Auswertung, Zustandsdiagramme, Stahl, Laminat, Ermüdung, Weibull,
Bruchmechanik, Härte, Korrosion, Kriechen, Werkstoffauswahl, Bericht und Server.

Die Sollwerte stammen, wo möglich, aus unabhängigen Formeln oder Normtabellen (nicht aus früheren Programmläufen).

Start:  python -m unittest discover -s tests   (im Ordner modules/werkstoffe)
"""
import base64
import io
import json
import math
import re
import struct
import sys
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from http.server import ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parents[1] / "sdk" / "python"))

from werk import bundle as B  # noqa: E402
from werk import corrcreep as CC  # noqa: E402
from werk import cryst as C  # noqa: E402
from werk import fatigue as F  # noqa: E402
from werk import formfactors as FF  # noqa: E402
from werk import hardness as H  # noqa: E402
from werk import laminate as LAM  # noqa: E402
from werk import phasediag as P  # noqa: E402
from werk import refs as RF  # noqa: E402
from werk import reliability as R  # noqa: E402
from werk import select as SE  # noqa: E402
from werk import steel as ST  # noqa: E402
from werk import tools as T  # noqa: E402
from werk import xrd as XR  # noqa: E402
from werk import xrdio as IO  # noqa: E402

LAM_CU = C.TUBES["Cu"][0]


def cu_pattern(fwhm=0.12, noise=3.0, seed=1, step=0.02):
    """Synthetisches Cu-Diagramm (Kα1 + Kα2) aus der eingebauten Struktur."""
    lines = C.reflections(C.phase("cu"), LAM_CU, 20, 120)
    x = np.arange(20, 120, step)
    y = C.profile(lines, x, fwhm, 0.5, C.TUBES["Cu"]) * 1000 + 50
    y = y + np.random.default_rng(seed).normal(0, noise, len(x))
    return x, y


def strongest(lines, n):
    return sorted(lines, key=lambda L: -L["Irel"])[:n]


# ============================================================================= Kristallographie
class CrystTest(unittest.TestCase):
    def test_formfactor_at_zero_is_Z(self):
        """f₀(s = 0) = Elektronenzahl (Cromer–Mann-Koeffizienten summieren sich auf Z)."""
        for el, Z in (("H", 1), ("C", 6), ("O", 8), ("Al", 13), ("Si", 14), ("Fe", 26), ("Cu", 29), ("W", 74)):
            self.assertAlmostEqual(float(FF.f0(el, np.array([0.0]))[0]), Z, delta=0.05 * Z if Z > 1 else 0.05, msg=el)
        self.assertLess(float(FF.f0("Cu", np.array([0.5]))[0]), 29)       # fällt mit sin θ/λ

    def test_bragg_and_cu_lines(self):
        """Cu (fcc, a = 3,6149 Å): erlaubt nur hkl alle gerade/ungerade; 2θ aus Bragg."""
        lines = C.reflections(C.phase("cu"), LAM_CU, 20, 120)
        self.assertEqual([L["hkl"] for L in lines], ["111", "200", "220", "311", "222", "400"])
        for L in lines:
            h = [int(c) for c in L["hkl"]]
            d = 3.6149 / math.sqrt(sum(v * v for v in h))
            self.assertAlmostEqual(L["d"], d, places=6)
            self.assertAlmostEqual(L["tth"], 2 * math.degrees(math.asin(LAM_CU / (2 * d))), places=6)
        self.assertEqual(strongest(lines, 1)[0]["hkl"], "111")
        self.assertEqual(lines[0]["m"], 8)
        self.assertEqual(lines[1]["m"], 6)

    def test_silicon_diamond_extinction(self):
        """Si (Diamant): 200 und 222 ausgelöscht (bei kugelsymmetrischen Atomen), 111 stärkste Linie."""
        lines = C.reflections(C.phase("si"), LAM_CU, 20, 100)
        hk = [L["hkl"] for L in lines]
        self.assertNotIn("200", hk)
        self.assertNotIn("222", hk)
        self.assertEqual(hk[:3], ["111", "220", "311"])
        self.assertEqual(strongest(lines, 1)[0]["hkl"], "111")

    def test_nacl_200_strongest(self):
        """NaCl: F(200) = 4(f_Na + f_Cl) > F(111) = 4(f_Cl − f_Na) → 200 stärkste, 111 schwach."""
        lines = C.reflections(C.phase("nacl"), LAM_CU, 20, 100)
        top = strongest(lines, 1)[0]
        self.assertEqual(top["hkl"], "200")
        L111 = next(L for L in lines if L["hkl"] == "111")
        self.assertLess(L111["Irel"], 20)

    def test_corundum_strong_lines(self):
        """α-Al₂O₃ (R-3c): die drei stärksten Linien bei 2θ ≈ 35,15 (104), 43,36 (113), 57,50 (116); 012 bei 25,58."""
        lines = C.reflections(C.phase("al2o3"), LAM_CU, 20, 70)
        top = sorted(L["tth"] for L in strongest(lines, 3))
        for got, want in zip(top, (35.15, 43.36, 57.50)):
            self.assertAlmostEqual(got, want, delta=0.05)
        self.assertTrue(any(abs(L["tth"] - 25.58) < 0.05 for L in lines))

    def test_density(self):
        """Röntgendichte Cu: 4 · 63,546 / (N_A · a³) = 8,93 g/cm³."""
        self.assertAlmostEqual(C.density(C.phase("cu")), 4 * 63.546 / 6.02214076e23 / (3.6149e-8) ** 3, places=2)

    def test_cif_rutile_equals_builtin(self):
        """Eine CIF mit Rutil (P4₂/mnm, 16 Operationen, nur asymmetrische Einheit) ergibt dasselbe Muster wie die
        eingebaute Phase mit ausgeschriebenen Lagen."""
        ops = ["x,y,z", "-x,-y,z", "-y+1/2,x+1/2,z+1/2", "y+1/2,-x+1/2,z+1/2", "-x+1/2,y+1/2,-z+1/2",
               "x+1/2,-y+1/2,-z+1/2", "y,x,-z", "-y,-x,-z", "-x,-y,-z", "x,y,-z", "y+1/2,-x+1/2,-z+1/2",
               "-y+1/2,x+1/2,-z+1/2", "x+1/2,-y+1/2,z+1/2", "-x+1/2,y+1/2,z+1/2", "-y,-x,z", "y,x,z"]
        cif = "\n".join(["data_rutile", "_chemical_name_mineral 'Rutile'", "_chemical_formula_sum 'O2 Ti'",
                         "_cell_length_a 4.5937(2)", "_cell_length_b 4.5937", "_cell_length_c 2.9587(3)",
                         "_cell_angle_alpha 90", "_cell_angle_beta 90", "_cell_angle_gamma 90",
                         "_symmetry_space_group_name_H-M 'P 42/m n m'", "loop_", "_symmetry_equiv_pos_as_xyz"]
                        + [f"'{o}'" for o in ops]
                        + ["loop_", "_atom_site_label", "_atom_site_type_symbol", "_atom_site_fract_x",
                           "_atom_site_fract_y", "_atom_site_fract_z", "Ti1 Ti 0 0 0", "O1 O 0.3049 0.3049 0"]) + "\n"
        p = C.parse_cif(cif)
        self.assertEqual(p["system"], "tetragonal")
        self.assertEqual(len(C.expand(p)), 6)                               # 2 Ti + 4 O je Zelle
        a = C.reflections(p, LAM_CU, 20, 90)
        b = C.reflections(C.phase("tio2-rutile"), LAM_CU, 20, 90)
        self.assertEqual(len(a), len(b))
        for x, y in zip(a, b):
            self.assertAlmostEqual(x["tth"], y["tth"], places=6)
            self.assertAlmostEqual(x["Irel"], y["Irel"], delta=0.05)
        self.assertEqual(strongest(a, 1)[0]["hkl"], "110")                    # Rutil: 110 stärkste Linie

    def test_cif_without_ops_refused(self):
        cif = "data_x\n_cell_length_a 4\n_cell_length_b 4\n_cell_length_c 4\n_symmetry_space_group_name_H-M 'F m -3 m'\n" \
              "loop_\n_atom_site_label\n_atom_site_fract_x\n_atom_site_fract_y\n_atom_site_fract_z\nCu 0 0 0\n"
        with self.assertRaises(C.CrystError):
            C.parse_cif(cif)

    def test_cubic_sequence(self):
        self.assertEqual([n for n, _ in C.cubic_sequence("fcc", 5)], [3, 4, 8, 11, 12])
        self.assertEqual([n for n, _ in C.cubic_sequence("bcc", 5)], [2, 4, 6, 8, 10])
        self.assertEqual([n for n, _ in C.cubic_sequence("diamond", 4)], [3, 8, 11, 16])

    def test_kristall_tool(self):
        r = T.run("kristall", {"phase": "si", "hkl": [1, 1, 1], "uvw": [1, 1, 0], "hkl2": [1, 0, 0]}, T.Ctx())
        self.assertAlmostEqual(r["plane"]["d"], 5.431 / math.sqrt(3), places=6)
        self.assertAlmostEqual(r["angle_planes"], math.degrees(math.acos(1 / math.sqrt(3))), places=6)
        self.assertAlmostEqual(r["direction"]["length"], 5.431 * math.sqrt(2), places=6)
        self.assertEqual(r["Z_atoms"], 8)


# ============================================================================= XRD-Leser
def _pattern():
    x = np.round(np.arange(20, 80, 0.05), 4)
    y = np.round(100 + 900 * np.exp(-((x - 43.3) / 0.2) ** 2), 2)
    return x, y


class ReaderTest(unittest.TestCase):
    def check(self, pat, x, y, lam1=None):
        self.assertEqual(len(pat.tth), len(x))
        np.testing.assert_allclose(pat.tth, x, atol=1e-6)
        np.testing.assert_allclose(pat.counts, y, rtol=1e-6, atol=1e-3)
        if lam1:
            self.assertAlmostEqual(pat.meta["lam1"], lam1, places=5)

    def test_xy_with_header(self):
        x, y = _pattern()
        txt = "# Wavelength: 1.54060 A\n# Anode Cu\n" + "\n".join(f"{a} {b}" for a, b in zip(x, y))
        self.check(IO.load(txt.encode(), "probe.xy"), x, y, 1.54060)

    def test_csv_decimal_comma(self):
        x, y = _pattern()
        txt = "2Theta;Intensität\n" + "\n".join(f"{a:.4f};{b:.2f}".replace(".", ",") for a, b in zip(x, y))
        self.check(IO.load(txt.encode("utf-8"), "probe.csv"), x, y)

    def test_anode_only_gives_standard_wavelength(self):
        x, y = _pattern()
        txt = "Anode: Co\n" + "\n".join(f"{a}\t{b}" for a, b in zip(x, y))
        p = IO.load(txt.encode(), "probe.txt")
        self.assertAlmostEqual(p.meta["lam1"], C.TUBES["Co"][0], places=5)
        self.assertTrue(any("Anode" in n for n in p.meta["notes"]))

    def test_xrdml(self):
        x, y = _pattern()
        xml = ('<?xml version="1.0" encoding="UTF-8"?>\n<xrdMeasurements xmlns="http://www.xrdml.com/XRDMeasurement/1.5">'
               '<xrdMeasurement><usedWavelength intended="K-Alpha 1"><kAlpha1 unit="Angstrom">1.5405980</kAlpha1>'
               '<kAlpha2 unit="Angstrom">1.5444260</kAlpha2><ratioKAlpha2KAlpha1>0.5</ratioKAlpha2KAlpha1></usedWavelength>'
               '<incidentBeamPath><xRayTube><anodeMaterial>Cu</anodeMaterial></xRayTube></incidentBeamPath>'
               '<scan><dataPoints><positions axis="2Theta" unit="deg"><startPosition>%s</startPosition>'
               '<endPosition>%s</endPosition></positions><positions axis="Omega" unit="deg"><startPosition>10</startPosition>'
               '<endPosition>40</endPosition></positions><commonCountingTime unit="seconds">1.0</commonCountingTime>'
               '<intensities unit="counts">%s</intensities></dataPoints></scan></xrdMeasurement></xrdMeasurements>'
               % (x[0], x[-1], " ".join(str(v) for v in y)))
        p = IO.load(xml.encode(), "probe.xrdml")
        self.check(p, x, y, 1.540598)
        self.assertAlmostEqual(p.meta["lam2"], 1.544426, places=6)
        self.assertEqual(p.meta["anode"], "Cu")

    def test_brml(self):
        x, y = _pattern()
        rows = "".join(f"<Datum>{k * 0.5},1,{a},{a / 2},{b}</Datum>" for k, (a, b) in enumerate(zip(x, y)))
        raw = ('<?xml version="1.0"?><RawData><FixedInformation><Instrument><PrimaryTracks><TrackInfoData><MountedOptics>'
               '<InfoData><Tube><WaveLengthAlpha1 Value="1.5406"/><WaveLengthAlpha2 Value="1.54439"/>'
               '<WaveLengthRatio Value="0.5"/><TubeMaterial>Cu</TubeMaterial></Tube></InfoData></MountedOptics>'
               '</TrackInfoData></PrimaryTracks></Instrument></FixedInformation><DataRoutes><DataRoute><DataViews/>'
               + rows + '</DataRoute></DataRoutes></RawData>')
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("Experiment0/RawData0.xml", raw)
            z.writestr("Experiment0/DataContainer.xml", "<x/>")
        self.check(IO.load(buf.getvalue(), "probe.brml"), x, y, 1.5406)

    def test_raw_v101(self):
        """Bruker RAW1.01 nach dem Aufbau in xylib: 712-Byte-Dateikopf, Bereichskopf 304 Byte, float32-Zählwerte."""
        x, y = _pattern()
        head = bytearray(712)
        head[0:7] = b"RAW1.01"
        struct.pack_into("<I", head, 12, 1)
        head[608:610] = b"Cu"
        struct.pack_into("<dd", head, 624, 1.5406, 1.54439)
        struct.pack_into("<d", head, 648, 0.5)
        rng = bytearray(304)
        struct.pack_into("<II", rng, 0, 304, len(x))
        struct.pack_into("<d", rng, 16, float(x[0]))
        struct.pack_into("<d", rng, 176, 0.05)
        struct.pack_into("<I", rng, 256, 0)
        data = bytes(head) + bytes(rng) + np.asarray(y, "<f4").tobytes()
        p = IO.load(data, "probe.raw")
        np.testing.assert_allclose(p.tth, x, atol=1e-6)
        np.testing.assert_allclose(p.counts, y.astype(np.float32), rtol=1e-6)
        self.assertAlmostEqual(p.meta["lam1"], 1.5406)

    def test_raw_v4_refused(self):
        with self.assertRaises(IO.XrdError) as cm:
            IO.load(b"RAW4.00" + bytes(800), "neu.raw")
        self.assertIn("Version 4", str(cm.exception))

    def test_uxd(self):
        x, y = _pattern()
        body = "\n".join(" ".join(f"{v}" for v in y[k:k + 8]) for k in range(0, len(y), 8))
        txt = f"; Bruker UXD\n_WL1=1.54060\n_WL2=1.54439\n_ANODE=Cu\n_2THETA={x[0]}\n_STEPSIZE=0.05\n{body}\n"
        self.check(IO.load(txt.encode(), "probe.uxd"), x, y, 1.5406)

    def test_ras_attenuator(self):
        x, y = _pattern()
        lines = ["*RAS_DATA_START", "*RAS_HEADER_START", '*HW_XG_TARGET_NAME "Cu"',
                 '*HW_XG_WAVE_LENGTH_ALPHA1 "1.540593"', "*RAS_HEADER_END", "*RAS_INT_START"]
        lines += [f"{a} {b / 2} 2.0" for a, b in zip(x, y)]                  # Zählwert × Abschwächer 2
        lines += ["*RAS_INT_END", "*RAS_DATA_END"]
        self.check(IO.load("\n".join(lines).encode("latin-1"), "probe.ras"), x, y, 1.540593)

    def test_bad_angle_column(self):
        txt = "\n".join(f"{v} {k}" for k, v in enumerate(np.linspace(500, 900, 50)))
        with self.assertRaises(IO.XrdError):
            IO.load(txt.encode(), "falsch.xy")


# ============================================================================= XRD-Auswertung
class XrdTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        x, y = cu_pattern()
        cls.ctx = T.Ctx({"p1": {"kind": "xrd", "name": "cu.xy", "obj": IO.from_columns(x, y, "cu.xy", {"anode": "Cu"})}})
        cls.r = T.run("xrd", {"item": "p1", "opt": {"phase_ref": "cu", "search": True, "overlay": ["cu"],
                                                    "quant_ids": ["cu"]}}, cls.ctx)

    def test_peaks_index_lattice(self):
        r = self.r
        self.assertEqual(len(r["peaks"]), 6)
        self.assertEqual(r["cubic"][0]["kind"], "fcc")
        self.assertAlmostEqual(r["cubic_refined"]["a"], 3.6149, delta=2e-4)
        self.assertAlmostEqual(r["cubic_refined"]["nr"]["a0"], 3.6149, delta=2e-4)
        tth = sorted(p["tth"] for p in r["peaks"])
        want = [L["tth"] for L in C.reflections(C.phase("cu"), LAM_CU, 20, 120)]
        for g, w in zip(tth, want):
            self.assertAlmostEqual(g, w, delta=0.01)

    def test_search_finds_cu(self):
        self.assertEqual(self.r["search"][0]["id"], "cu")
        self.assertGreater(self.r["search"][0]["score"], 90)
        self.assertEqual(self.r["sticks"][0]["id"], "cu")

    def test_scherrer(self):
        """D = K λ / (β cos θ), β in rad (Breite nach Abzug der Geräteverbreiterung; hier keine)."""
        p = next(p for p in self.r["peaks"] if p.get("D_nm"))
        th = math.radians(p["tth"] / 2)
        D = 0.9 * self.r["lam1"] / (math.radians(p["b_sample"]) * math.cos(th)) / 10
        self.assertAlmostEqual(p["D_nm"], D, delta=1e-6 * D)

    def test_bragg_d(self):
        for p in self.r["peaks"]:
            self.assertAlmostEqual(p["d"], self.r["lam1"] / (2 * math.sin(math.radians(p["tth"] / 2))), places=6)

    def test_index_cubic_direct(self):
        d = [3.6149 / math.sqrt(n) for n in (3, 4, 8, 11, 12, 16)]
        top = XR.index_cubic(d)[0]
        self.assertEqual(top["kind"], "fcc")
        self.assertAlmostEqual(top["a"], 3.6149, places=4)
        d = [2.8665 / math.sqrt(n) for n in (2, 4, 6, 8, 10)]
        self.assertEqual(XR.index_cubic(d)[0]["kind"], "bcc")

    def test_williamson_hall_recovers_size_and_strain(self):
        """β cos θ = Kλ/D + 4 ε sin θ: synthetische Breiten aus D = 40 nm, ε = 0,002 werden zurückgewonnen."""
        tth = np.array([30.0, 45, 60, 75, 90, 105])
        th = np.radians(tth / 2)
        beta = (0.9 * LAM_CU / 400 + 4 * 0.002 * np.sin(th)) / np.cos(th)
        wh = XR.williamson_hall(tth, np.degrees(beta), LAM_CU)
        self.assertAlmostEqual(wh["D_nm"], 40.0, delta=0.01)
        self.assertAlmostEqual(wh["strain"], 0.002, delta=1e-6)

    def test_missing_item(self):
        with self.assertRaises(LookupError):                                   # Server: 404
            T.run("xrd", {"item": "fehlt", "opt": {}}, T.Ctx())


# ============================================================================= Zustandsdiagramme
class PhaseTest(unittest.TestCase):
    def test_fe_c_lever_and_constituents(self):
        """Fe–Fe₃C, 0,35 % C knapp unter 727 °C: Gefüge (0,76 − 0,35)/(0,76 − 0,022) voreutektoider Ferrit."""
        s = P.system("fe-c")
        parts = P.constituents(s, 0.35)[0]["parts"]
        self.assertAlmostEqual(parts[0]["frac"], (0.76 - 0.35) / (0.76 - 0.022), places=6)
        self.assertAlmostEqual(parts[1]["frac"], (0.35 - 0.022) / (0.76 - 0.022), places=6)
        lv = P.lever(s, 0.35, 726)
        a, c = lv["phases"]
        self.assertAlmostEqual(a["frac"], (c["x"] - 0.35) / (c["x"] - a["x"]), places=9)
        self.assertAlmostEqual(a["frac"] + c["frac"], 1, places=12)

    def test_pb_sn_lever(self):
        """Pb–Sn, 40 Gew.-% Sn bei 150 °C: α-Anteil = (Cβ − C0)/(Cβ − Cα) mit den zitierten Solvus-Eckpunkten."""
        lv = P.lever(P.system("pb-sn"), 40, 150)
        a, b = lv["phases"]
        self.assertEqual(lv["region"], "α + β")
        self.assertAlmostEqual(a["frac"], (b["x"] - 40) / (b["x"] - a["x"]), places=9)
        self.assertAlmostEqual(a["frac"], 0.67, delta=0.02)        # Callister, Beispiel 9.3: W_α = 0,67

    def test_single_phase_region(self):
        lv = P.lever(P.system("fe-c"), 0.4, 900)
        self.assertEqual(len(lv["phases"]), 1)
        self.assertAlmostEqual(lv["phases"][0]["frac"], 1.0)

    def test_cu_ni_ideal_solution(self):
        """Ideale Lösung in Flüssigkeit und Mischkristall: x_S/x_L = exp(ΔG_B/RT), (1−x_S)/(1−x_L) = exp(ΔG_A/RT),
        ΔG = ΔH(1 − T/T_m). Geschlossene Lösung gegen die numerische Gleichgewichtsrechnung."""
        p = P.preset("cu-ni")
        T_C = 1225.0
        TK, Rg = T_C + 273.15, 8.314462618
        kA = math.exp(p["HA"] * 1e3 * (1 - TK / (p["TmA"] + 273.15)) / (Rg * TK))
        kB = math.exp(p["HB"] * 1e3 * (1 - TK / (p["TmB"] + 273.15)) / (Rg * TK))
        xL = (1 - kA) / (kB - kA)
        xS = kB * xL

        def wt(x):
            return 100 * x * p["MB"] / (x * p["MB"] + (1 - x) * p["MA"])
        lv = P.lever_computed(p, 35.0, T_C, "wt")
        L, S = lv["phases"]
        self.assertAlmostEqual(L["x"], wt(xL), delta=0.15)
        self.assertAlmostEqual(S["x"], wt(xS), delta=0.15)
        self.assertAlmostEqual(L["frac"], (wt(xS) - 35) / (wt(xS) - wt(xL)), delta=0.01)

    def test_computed_diagram_end_points(self):
        p = P.preset("cu-ni")
        d = P.computed_diagram(p, nT=81, n=401)
        liq = np.array(d["points"]["liquidus"])
        self.assertAlmostEqual(liq[:, 1].max(), p["TmB"], delta=6)
        self.assertAlmostEqual(liq[:, 1].min(), p["TmA"], delta=6)
        sol = np.array(d["points"]["solidus"])
        for x, Tl in liq[::10]:                                        # Solidus liegt unter der Liquidus
            Ts = np.interp(x, sol[:, 0], sol[:, 1])
            self.assertLessEqual(Ts, Tl + 1e-6)

    def test_phasen_tool_marks_schematic(self):
        r = T.run("phasen", {"system": "fe-c", "x": 0.35, "T": 726}, T.Ctx())
        self.assertTrue(r["refs"])
        self.assertIn("cooling", r)


# ============================================================================= Stahl
class SteelTest(unittest.TestCase):
    def test_carbon_equivalents(self):
        """IIW CE = C + Mn/6 + (Cr+Mo+V)/5 + (Ni+Cu)/15; Pcm (Ito–Bessyo); CET (EN 1011-2)."""
        c = {"C": 0.18, "Mn": 1.4, "Si": 0.3, "Cr": 0.1, "Mo": 0.02, "Ni": 0.1, "Cu": 0.1, "V": 0.01}
        r = ST.composition_report(c)
        self.assertAlmostEqual(r["CE"], 0.18 + 1.4 / 6 + (0.1 + 0.02 + 0.01) / 5 + (0.1 + 0.1) / 15, places=9)
        self.assertAlmostEqual(r["Pcm"], 0.18 + 0.3 / 30 + (1.4 + 0.1 + 0.1) / 20 + 0.1 / 60 + 0.02 / 15 + 0.01 / 10, places=9)
        self.assertAlmostEqual(r["CET"], 0.18 + (1.4 + 0.02) / 10 + (0.1 + 0.1) / 20 + 0.1 / 40, places=9)

    def test_hollomon_jaffe(self):
        r = ST.hollomon_jaffe(T_C=600, t_h=2, C=20)
        self.assertAlmostEqual(r["P"], 873.15 * (20 + math.log10(2)), places=6)
        e = ST.equivalent_tempering(600, 2, 650, 20)
        self.assertAlmostEqual(923.15 * (20 + math.log10(e["t2_h"])), r["P"], places=4)

    def test_carburising_depth(self):
        """c(x) = c_s − (c_s − c_0) erf(x / 2√(Dt)); an der Einsatzhärtetiefe ist c = Grenzwert."""
        r = ST.carburise_profile(0.2, 0.9, 925, 4, c_limit=0.4)
        x = r["depth_mm"] * 1e-3
        c = 0.9 - 0.7 * math.erf(x / (2 * math.sqrt(r["D"] * 4 * 3600)))
        self.assertAlmostEqual(c, 0.4, places=4)
        self.assertAlmostEqual(r["D"], 2.3e-5 * math.exp(-148e3 / (8.314462618 * 1198.15)), delta=0.02 * r["D"])

    def test_preheat_increases_with_cet(self):
        a = ST.preheat_temp(0.30, 20, 5, 1.5)["Tp"]
        b = ST.preheat_temp(0.40, 20, 5, 1.5)["Tp"]
        self.assertGreater(b, a)


# ============================================================================= Laminat
class LaminateTest(unittest.TestCase):
    def test_isotropic(self):
        """Isotropes Material: jeder Lagenaufbau gibt E_x = E, ν_xy = ν, G_xy = E/2(1+ν)."""
        E, nu = 70.0, 0.3
        r = LAM.analyse({"E1": E, "E2": E, "G12": E / (2 * (1 + nu)), "nu12": nu}, LAM.parse_layup("[0/45/-45/90]s"), 0.125)
        self.assertAlmostEqual(float(r["eng"]["Ex"]), E, places=6)
        self.assertAlmostEqual(float(r["eng"]["nuxy"]), nu, places=6)
        self.assertAlmostEqual(float(r["eng"]["Gxy"]), E / (2 * (1 + nu)), places=6)

    def test_cross_ply_symmetric(self):
        r = LAM.analyse({"E1": 147, "E2": 10.3, "G12": 7, "nu12": 0.27}, LAM.parse_layup("[0/90]s"), 0.125)
        A, Bm = np.array(r["A"]), np.array(r["B"])
        self.assertAlmostEqual(A[0, 0], A[1, 1], delta=1e-9 * A[0, 0])
        self.assertLess(abs(A[0, 2]), 1e-9 * A[0, 0])
        self.assertLess(np.abs(Bm).max(), 1e-9 * A[0, 0])
        self.assertTrue(r["symmetric"])
        Q = LAM.q_matrix(147, 10.3, 7, 0.27)
        self.assertAlmostEqual(A[0, 0], (Q[0, 0] + Q[1, 1]) * 0.25, delta=1e-6 * A[0, 0])  # Q in MPa, A in N/mm

    def test_ud_first_ply_failure(self):
        """[0]₄ unter N_x: σ₁ = N_x/h, Reservefaktor Höchstspannung = X_t h / N_x."""
        ply = {"E1": 147, "E2": 10.3, "G12": 7, "nu12": 0.27, "Xt": 2280, "Xc": 1725, "Yt": 57, "Yc": 228, "S12": 76}
        r = LAM.analyse(ply, [0, 0, 0, 0], 0.125, N=(100, 0, 0))
        self.assertAlmostEqual(r["fpf"]["maxstress"]["R"], 2280 * 0.5 / 100, places=6)

    def test_layup_parser(self):
        self.assertEqual(LAM.parse_layup("[0/±45/90]s"), [0, 45, -45, 90, 90, -45, 45, 0])
        self.assertEqual(LAM.parse_layup("[0/90]2s"), [0, 90, 0, 90, 90, 0, 90, 0])
        with self.assertRaises(LAM.LamError):
            LAM.parse_layup("[0/abc]")


# ============================================================================= Ermüdung
class FatigueTest(unittest.TestCase):
    def test_rainflow_e1049_example(self):
        """ASTM E1049-85 Bild 6: Bereiche 3 (½), 4 (1½), 6 (½), 8 (1), 9 (½)."""
        cyc = F.rainflow([-2, 1, -3, 5, -1, 3, -4, 4, -2])
        agg = {}
        for c in cyc:
            agg[c["range"]] = agg.get(c["range"], 0) + c["count"]
        self.assertEqual(agg, {3.0: 0.5, 4.0: 1.5, 6.0: 0.5, 8.0: 1.0, 9.0: 0.5})

    def test_basquin_recovers(self):
        """σa = σf′ (2N)^b mit σf′ = 900 MPa, b = −0,09 wird ohne Streuung exakt zurückgewonnen."""
        sa = np.array([500, 450, 400, 350, 300.0])
        N = (sa / 900) ** (1 / -0.09) / 2
        fit = F.basquin_fit(sa, N)["lsq"]
        self.assertAlmostEqual(fit["b"], -0.09, places=6)
        self.assertAlmostEqual(fit["sigma_f"], 900, delta=1e-3)
        self.assertAlmostEqual(F.life(420, fit), (420 / 900) ** (1 / -0.09) / 2, delta=1e-6 * F.life(420, fit))

    def test_runouts_shift_mle(self):
        sa = [400, 360, 330, 300, 280, 265, 255, 255]
        N = [1.2e4, 3.9e4, 9.5e4, 2.4e5, 6.1e5, 1.5e6, 1e7, 1e7]
        r = F.basquin_fit(sa, N, [0, 0, 0, 0, 0, 0, 1, 1])
        self.assertIn("mle", r)
        self.assertGreater(F.life(255, r["mle"]), F.life(255, r["lsq"]))      # Durchläufer ziehen die Linie nach rechts

    def test_mean_stress_models(self):
        self.assertAlmostEqual(F.equivalent(200, 100, "goodman", Rm=800), 200 / (1 - 100 / 800))
        self.assertAlmostEqual(F.equivalent(200, 100, "gerber", Rm=800), 200 / (1 - (100 / 800) ** 2))
        self.assertAlmostEqual(F.equivalent(200, 100, "soderberg", Re=600), 200 / (1 - 100 / 600))
        self.assertAlmostEqual(F.equivalent(200, 100, "swt"), math.sqrt(300 * 200))
        self.assertIsNone(F.equivalent(200, -300, "swt"))

    def test_marin(self):
        """Shigley: ka = 4,51 Rm^−0,265 (bearbeitet), kb = 1,24 d^−0,107 (2,79–51 mm), Se′ = 0,5 Rm."""
        r = F.marin(800, "bearbeitet", 10, "biegung")
        self.assertAlmostEqual(r["ka"], 4.51 * 800 ** -0.265, places=6)
        self.assertAlmostEqual(r["kb"], 1.24 * 10 ** -0.107, places=6)
        self.assertAlmostEqual(r["Se"], r["ka"] * r["kb"] * 400, places=6)
        self.assertEqual(F.marin(1600)["Se_prime"], 700)

    def test_miner(self):
        fit = F._basq(20.0, -6.0)
        cyc = [{"range": 600.0, "mean": 0.0, "count": 2.0}]
        r = F.miner(cyc, fit, model="none")
        self.assertAlmostEqual(float(r["D"]), 2 / F.life(300, fit), places=12)


# ============================================================================= Weibull, Bruchmechanik
class ReliabilityTest(unittest.TestCase):
    X = [312, 341, 355, 368, 377, 386, 395, 402, 410, 418, 427, 436, 449, 466]

    def test_mle_score_equations(self):
        """MLE: Σ xᵐ ln x / Σ xᵐ − 1/m − mean(ln x) = 0 und σ₀ = (mean xᵐ)^(1/m)."""
        r = R.weibull_mle(self.X)
        x, m = np.array(self.X, float), r["m"]
        g = np.sum(x ** m * np.log(x)) / np.sum(x ** m) - 1 / m - np.mean(np.log(x))
        self.assertLess(abs(g), 1e-8)
        self.assertAlmostEqual(float(r["sigma0"]), float(np.mean(x ** m) ** (1 / m)), places=6)

    def test_lsq_median_ranks(self):
        r = R.weibull_lsq(self.X)
        n = len(self.X)
        np.testing.assert_allclose(r["F"], [(i - 0.3) / (n + 0.4) for i in range(1, n + 1)])

    def test_bootstrap_reproducible(self):
        a = R.bootstrap(self.X, B=200, seed=7)
        b = R.bootstrap(self.X, B=200, seed=7)
        self.assertEqual(a["m_ci"], b["m_ci"])
        self.assertLess(a["m_ci"][0], a["m"])
        self.assertGreater(a["m_ci"][1], a["m"])

    def test_size_effect(self):
        self.assertAlmostEqual(R.size_scale(400, 10, 1.0, 10.0), 400 * 0.1 ** 0.1, places=9)

    def test_e399_factors(self):
        """ASTM E399: f(0,5) = 2,6625 (SE(B), S = 4W) und 9,659 (C(T))."""
        self.assertAlmostEqual(R.f_senb(0.5), 2.6625, places=4)
        self.assertAlmostEqual(R.f_ct(0.5), 9.659, places=3)

    def test_kq(self):
        """K_Q = P S / (B W^1,5) · f(a/W) für SE(B)."""
        r = R.k_q("senb", 12, 20, 40, 20, Rp=800, Pmax_kN=12.5)
        K = 12e3 * 160 / (20 * 40 ** 1.5) * R.f_senb(0.5) / math.sqrt(1000)
        self.assertAlmostEqual(r["K"], K, places=6)

    def test_critical_crack(self):
        r = R.critical_crack(50, 300)
        self.assertAlmostEqual(r["a_c_mm"], (50 / 300) ** 2 / math.pi * 1e3, places=6)
        self.assertAlmostEqual(R.critical_stress(50, r["a_c_mm"]), 300, places=6)


# ============================================================================= Härte, Korngrösse
class HardnessTest(unittest.TestCase):
    def test_vickers_brinell_knoop(self):
        self.assertAlmostEqual(H.vickers(98.07, 0.3, 0.3)["value"], 0.1891 * 98.07 / 0.09, places=9)
        self.assertEqual(H.vickers(98.07, 0.3)["scale"], "HV10")
        D, d, Fn = 10, 4, 29420
        self.assertAlmostEqual(H.brinell(Fn, D, d)["value"],
                               0.102 * 2 * Fn / (math.pi * D * (D - math.sqrt(D * D - d * d))), places=9)
        self.assertAlmostEqual(H.knoop(9.807, 0.1)["value"], 1.451 * 9.807 / 0.01, places=9)

    def test_e112_table(self):
        """ASTM E112 Tabelle 4: G = 0 ↔ ℓ̄ = 0,320 mm, G = 8 ↔ ℓ̄ = 0,0200 mm."""
        self.assertAlmostEqual(H.grain_intercept(0.320, 1)["G"], 0.0, delta=0.02)
        self.assertAlmostEqual(H.grain_intercept(20.0, 1000)["G"], 8.0, delta=0.02)
        self.assertAlmostEqual(H.grain_planimetric(1)["G"], -2.954, places=6)

    def test_hall_petch(self):
        d = np.array([5.0, 10, 25, 60])
        s = 150 + 0.5 * (d * 1e-6) ** -0.5
        r = H.hall_petch(d, s)
        self.assertAlmostEqual(r["sigma0"], 150, places=6)
        self.assertAlmostEqual(r["k"], 0.5, places=9)

    def test_conversion_needs_table_and_no_extrapolation(self):
        t = H.parse_table("# Quelle: eigene Tabelle\nHV;HRC\n200;10\n300;30\n400;41\n")
        self.assertEqual(t["source"], "eigene Tabelle")
        self.assertAlmostEqual(H.convert(t, 250, "HV", "HRC")["value"], 20.0)
        self.assertIsNone(H.convert(t, 500, "HV", "HRC")["value"])
        self.assertAlmostEqual(H.rule_of_thumb_Rm(200)["value"], 660)

    def test_tool_without_table_shows_rule_only(self):
        r = T.run("haerte", {"method": "HV", "indents": [{"F": 98.07, "d1": 0.3, "d2": 0.302}]}, T.Ctx())
        self.assertNotIn("converted", r)
        self.assertAlmostEqual(r["rule"]["value"], 3.3 * r["stats"]["mean"], places=6)


# ============================================================================= Korrosion, Kriechen
class CorrCreepTest(unittest.TestCase):
    @staticmethod
    def bv(Ec=-0.55, ic=10.0, ba=0.06, bc=0.12):
        E = np.linspace(-0.75, -0.35, 201)
        return E, ic * 1e-6 * (10 ** ((E - Ec) / ba) - 10 ** (-(E - Ec) / bc))

    def test_tafel_and_bv_recover(self):
        E, i = self.bv()
        r = CC.tafel(E, i, "A", 1.0, bv=True)
        self.assertAlmostEqual(r["bv"]["icorr"], 10.0, delta=1e-4)
        self.assertAlmostEqual(r["bv"]["ba"], 60.0, delta=1e-3)
        self.assertAlmostEqual(r["bv"]["bc"], 120.0, delta=1e-3)
        self.assertAlmostEqual(r["icorr"], 10.0, delta=0.6)                # Tafelgeraden: Rückstrom verfälscht leicht
        self.assertAlmostEqual(r["Ecorr"], -0.55, delta=2e-3)

    def test_units_and_area(self):
        E, i = self.bv()
        a = CC.tafel(E, i, "A", 1.0, bv=True)["bv"]["icorr"]
        b = CC.tafel(E, i * 1e3, "mA", 2.0, bv=True)["bv"]["icorr"]
        self.assertAlmostEqual(b, a / 2, delta=1e-6)

    def test_corrosion_rate_g102(self):
        """ASTM G102: CR [mm/a] = 3,27·10⁻³ · i_corr [µA/cm²] · EW / ρ."""
        ew = CC.equivalent_weight("Fe")
        r = CC.corrosion_rate(10.0, ew["EW"], ew["rho"])
        self.assertAlmostEqual(r["mm_a"], 3.27e-3 * 10 * 55.845 / 2 / ew["rho"], delta=1e-3 * r["mm_a"])

    def test_lmp_roundtrip(self):
        """Exakte Daten lg σ = 4 − 1,0·10⁻⁴ P (C = 20) werden mit Grad 1 zurückgewonnen; Vorhersage = Umkehrung."""
        T_C = np.array([550, 575, 600, 625, 650.0])
        t = np.array([1000, 2000, 3000, 800, 400.0])
        Pv = (T_C + 273.15) * (20 + np.log10(t))
        s = 10 ** (4 - 1e-4 * Pv)
        fit = CC.lmp_fit(s, T_C, t, C=20, deg=1)
        self.assertGreater(fit["r2"], 0.999999)
        pr = CC.lmp_predict(fit, float(s[2]), 600)
        self.assertAlmostEqual(pr["t_h"], 3000, delta=0.01)

    def test_norton_arrhenius(self):
        """ε̇ = A σⁿ exp(−Q/RT), n = 5, Q = 280 kJ/mol."""
        sig = np.array([60, 80, 100, 60, 80, 100.0])
        T_C = np.array([600, 600, 600, 650, 650, 650.0])
        rate = 1e-12 * sig ** 5 * np.exp(-280e3 / (8.314462618 * (T_C + 273.15))) * 1e14
        r = CC.norton_fit(rate, sig, T_C)
        self.assertAlmostEqual(r["n"], 5.0, places=6)
        self.assertAlmostEqual(r["Q_kJ"], 280.0, delta=0.01)


# ============================================================================= Auswahl
class SelectTest(unittest.TestCase):
    def test_rank_order_and_index(self):
        r = SE.rank({"E": 0.5, "rho": -1.0})
        M = [x["M"] for x in r["ranked"]]
        self.assertEqual(M, sorted(M, reverse=True))
        self.assertGreater(r["n_ok"], 20)
        self.assertFalse(any(x["mp"] for x in r["ranked"]))                 # berechnete MP-Daten nur auf Wunsch

    def test_limits(self):
        r = SE.rank({"E": 0.5, "rho": -1.0}, limits=[{"prop": "rho", "max": 3.0}])
        for x in r["ranked"]:
            self.assertTrue(x["M"] is not None)
        names = {x["id"] for x in r["ranked"]}
        self.assertTrue(r["excluded"])
        self.assertTrue(names)

    def test_chart_and_cards(self):
        r = T.run("auswahl", {"x": "rho", "y": "E", "index": "beam_E"}, T.Ctx())
        self.assertEqual(r["slope"], 2.0)
        self.assertTrue(all(p["x"] and p["y"] for p in r["points"]))
        k = T.run("karten", {"names": ["Kupfer (rein)"]}, T.Ctx())
        self.assertEqual(k["cards"][0]["id"], "cu-rein")
        for w in k["cards"][0]["werte"]:
            self.assertTrue(w["source"] or w["key"], w)                     # jeder Wert mit Quelle

    OWN = [{"name": "Mein Al", "x": 2.7, "y": 70, "src": "Datenblatt X"}, {"name": "Probe B", "x": 1.5, "y": 20, "src": ""}]

    def test_own_points_ranked_by_axes(self):
        r = T.run("auswahl", {"x": "rho", "y": "E", "index": "beam_E", "own": self.OWN}, T.Ctx())
        self.assertEqual([p["id"] for p in r["own"]], ["own-1", "own-2"])
        mine = {x["name"]: x for x in r["rank"]["ranked"] if x.get("own")}
        self.assertAlmostEqual(mine["Mein Al"]["M"], 70 ** 0.5 / 2.7, places=9)     # M = E^1/2 / rho
        self.assertAlmostEqual(mine["Probe B"]["M"], 20 ** 0.5 / 1.5, places=9)
        M = [x["M"] for x in r["rank"]["ranked"]]
        self.assertEqual(M, sorted(M, reverse=True))
        self.assertEqual([x["rank"] for x in r["rank"]["ranked"]], list(range(1, len(M) + 1)))
        self.assertEqual(r["rank"]["n_ok"], len(M))

    def test_own_points_need_axes_only_index_and_limits(self):
        r = T.run("auswahl", {"x": "rho", "y": "E", "expo": {"Rp": 1, "rho": -1}, "own": self.OWN[:1]}, T.Ctx())
        self.assertFalse(any(x.get("own") for x in r["rank"]["ranked"]))
        self.assertTrue(any(x.get("own") for x in r["rank"]["excluded"]))
        r = T.run("auswahl", {"x": "rho", "y": "E", "index": "beam_E", "own": self.OWN[:1],
                              "limits": [{"prop": "rho", "max": 2.0}]}, T.Ctx())
        ex = [x for x in r["rank"]["excluded"] if x.get("own")]
        self.assertEqual(len(ex), 1)
        self.assertIn("2.7 > 2", ex[0]["why"][0])

    def test_own_points_validated(self):
        for bad in ({"name": "", "x": 1, "y": 1}, {"name": "a", "x": 0, "y": 1}, {"name": "a", "x": "z", "y": 1}):
            with self.subTest(bad=bad), self.assertRaises(T.ERRORS):
                T.run("auswahl", {"x": "rho", "y": "E", "own": [bad]}, T.Ctx())


# ============================================================================= Gittermodell (KG)
class GitterTest(unittest.TestCase):
    OFF = {k: False for k in ("vac", "vib", "distort", "precip", "disl", "sf", "gb")}

    def build(self, **req):
        from werk import gitter as GT
        return GT.build({"n": 4, "seed": 1, **req}, "de")

    def test_austenite_carbon_on_octahedral_sites(self):
        r = self.build(host="Fe", T=1000, solutes=[{"el": "C", "c": 0.4, "einheit": "wt"}])
        self.assertEqual(r["phase"]["gitter_id"], "kfz")
        s = r["solutes"][0]
        self.assertEqual(s["site"], "okt")
        self.assertLessEqual(abs(s["placed"] - s["expected"]), 1)                # wahre Zahl, stochastisch gerundet
        x = s["x_at"]
        n_fe = sum(1 for a in r["atoms"] if r["kinds"][a[3]]["role"] == "host")
        self.assertAlmostEqual(s["expected"], x / (1 - x) * n_fe, delta=0.5)

    def test_ferrite_cementite_by_lever_rule(self):
        r = self.build(host="Fe", T=20, solutes=[{"el": "C", "c": 0.8, "einheit": "wt"}])
        cem = [p for p in r["phase"]["phases"] if "Fe" in p["name"] and "C" in p["name"]]
        self.assertTrue(cem)
        self.assertAlmostEqual(cem[0]["frac"], 0.8 / 6.69, delta=0.01)           # (0,8 − ~0) / (6,69 − ~0)

    def test_vacancies_arrhenius_and_boost(self):
        from werk import gitter as GT
        r = self.build(host="Ni", T=900, boost=1e6)
        v = r["vac"]
        T_K = 900 + 273.15
        self.assertAlmostEqual(v["c"], math.exp(v["Sv"]) * math.exp(-v["Hv"] / (GT.K_EV * T_K)), delta=v["c"] * 1e-9)
        self.assertAlmostEqual(v["expected"], v["c"] * v["sites"], delta=v["expected"] * 1e-9)
        self.assertLess(abs(v["placed"] - v["expected"] * 1e6), 4 * math.sqrt(v["expected"] * 1e6) + 2)
        r0 = self.build(host="Ni", T=20)
        self.assertEqual(r0["vac"]["placed"], 0)                                 # Raumtemperatur: keine Leerstelle im Bild

    def test_debye_high_temperature_limit(self):
        from werk import gitter as GT
        m, th, T = 58.69, 450.0, 3000.0
        u2 = GT.debye_u2(m, th, T)
        classic = 3 * GT.HBAR ** 2 * T / (m * GT.U_KG * GT.K_J * th ** 2) * 1e20     # Å²
        self.assertAlmostEqual(u2 / classic, 1.0, delta=0.01)
        self.assertGreater(GT.debye_u2(m, th, 1.0), 0)                           # Nullpunktsschwingung

    def test_unit_cell_on_atoms_and_coordination(self):
        for host, n_cell in (("Cu", 14), ("Fe", 9), ("Mg", None)):
            with self.subTest(host=host):
                r = self.build(host=host, T=20, fx=self.OFF)
                P = np.asarray(r["atoms"], float)[:, :3]
                C = np.asarray(r["cell"]["corners"], float)
                d = np.sqrt(((C[:, None] - P[None]) ** 2).sum(-1)).min(1)
                self.assertLess(d.max(), 1e-3)                                    # Ecken der Zelle sitzen auf Atomen
                self.assertEqual(len(r["cell"]["edges"]), 12)
                if n_cell:
                    f = np.linalg.solve(np.stack([C[4] - C[0], C[2] - C[0], C[1] - C[0]], 1), (P - C[0]).T).T
                    self.assertEqual(int(np.all((f > -1e-3) & (f < 1 + 1e-3), axis=1).sum()), n_cell)

    def test_slice_layers(self):
        cases = (("Ni", "111", 6), ("Ni", "100", 4), ("Fe", "110", 4), ("Ti", "0001", 6))
        for host, plane, coord in cases:
            with self.subTest(host=host, plane=plane):
                r = self.build(host=host, T=20, n=5, fx=self.OFF)
                Q = CH_slice(r, plane)[0]
                d = np.sqrt(((Q[:, None] - Q[None]) ** 2).sum(-1))
                np.fill_diagonal(d, 1e9)
                inner = np.abs(Q).max(1) < 0.5 * np.abs(Q).max()
                d1 = np.median(d.min(1))
                expect = r["lattice"]["a"] if plane == "0001" else r["lattice"]["dnn"]  # hdp: Basisebene im Abstand a
                self.assertAlmostEqual(d1, expect, delta=0.02)
                self.assertEqual(int(np.bincount((d[inner] < d1 * 1.05).sum(1)).argmax()), coord)

    def test_melt_defects_and_determinism(self):
        r = self.build(host="Cu", T=1200)
        self.assertTrue(r["liquid"])
        self.assertIsNone(r["cell"])
        a = self.build(host="Ni", T=500, fx={"disl": True, "sf": True})
        b = self.build(host="Ni", T=500, fx={"disl": True, "sf": True})
        self.assertEqual(a["atoms"], b["atoms"])
        self.assertTrue(a["disl"] and a["sf"])
        g = self.build(host="Ni", T=500, fx={"gb": True, "sf": True}, gb_angle=20)
        self.assertEqual(g["gb"]["angle"], 20)
        self.assertTrue(any("Korngrenze" in n for n in g["notes"]))

    def test_own_limit_with_source_in_report(self):
        # ein Paar ohne hinterlegtes Diagramm (Al–Mn hat inzwischen eines; das Diagramm geht dann vor)
        req = {"host": "Al", "T": 20, "n": 5, "seed": 1, "solutes": [{"el": "Cr", "c": 3, "einheit": "wt"}],
               "limits": {"Cr": 0.2}, "limit_src": {"Cr": "Eigene Quelle 2020, https://example.org/mn.pdf"}}
        r = T.run("gitter", req, T.Ctx())
        s = r["solutes"][0]
        self.assertEqual(s["how"], "eigen")
        self.assertGreater(s.get("excess_atoms", 0), 0)
        b = B.build({"sections": [{"tool": "gitter", "req": req}], "lang": "de"}, T.Ctx(), {})
        files = {k: base64.b64decode(v).decode("utf-8", "replace") for k, v in b["files"].items()}
        self.assertIn("url = {https://example.org/mn.pdf}", files["refs.bib"])
        ids = {it.get("id") for it in b["items"]}
        self.assertTrue({"gitter-gitter", "gitter-zelle", "gitter-kennwerte", "gitter-atome"} <= ids)
        meth = files["text-methodik.tex"]
        for s_ in ("c_v = \\exp", "\\langle u_x^2\\rangle", "u(r) = \\delta"):
            self.assertIn(s_, meth)

    def test_figure_style_in_request_redraws_that_figure(self):
        """A styled variant in the report: the hub sends styles {figure id: spec} with the stored request."""
        req = {"host": "Al", "T": 20, "n": 5, "seed": 1, "solutes": []}
        base = B.build({"sections": [{"tool": "gitter", "req": req}], "lang": "de"}, T.Ctx(), {})
        fig = next(it for it in base["items"] if it["kind"] == "figure")
        b = B.build({"sections": [{"tool": "gitter", "req": req}], "lang": "de", "describe_figures": True,
                     "styles": {fig["id"]: {"preset": "elsevier-1"}}}, T.Ctx(), {})
        it = next(i for i in b["items"] if i.get("id") == fig["id"])
        self.assertEqual(it["style"]["preset"], "elsevier-1")
        self.assertAlmostEqual(it["describe"]["now"]["width_mm"], 90, places=0)
        self.assertNotAlmostEqual(it["describe"]["width_mm"], 90, places=0)   # as the module draws it
        self.assertNotIn("style", next(i for i in base["items"] if i.get("id") == fig["id"]))
        self.assertEqual(b["source"]["request"]["styles"], {fig["id"]: {"preset": "elsevier-1"}})


def CH_slice(res, plane):
    from werk import charts as CH
    return CH.slice_points(res, plane)


# ============================================================================= alle Werkzeuge, Quellen
def all_cases():
    x, y = cu_pattern()
    ctx = T.Ctx({"p1": {"kind": "xrd", "name": "cu.xy", "obj": IO.from_columns(x, y, "cu.xy", {"anode": "Cu"})},
                 "t1": {"kind": "hardtable", "name": "conv.csv", "obj": "# Quelle: eigene Tabelle\nHV;HRC\n200;10\n300;30\n400;41\n"}})
    E, i = CorrCreepTest.bv()
    secs = [
        ("auswahl", {"x": "rho", "y": "E", "index": "beam_E",
                     "own": [{"name": "Mein Al", "x": 2.7, "y": 70, "src": "Datenblatt X, https://example.org/ds.pdf"},
                             {"name": "Probe B", "x": 1.5, "y": 20, "src": ""}]}),
        ("karten", {"names": ["Kupfer (rein)", "Aluminium (rein)"]}),
        ("kristall", {"phase": "si", "hkl": [1, 1, 1], "uvw": [1, 1, 0], "hkl2": [1, 0, 0]}),
        ("gitter", {"host": "Fe", "T": 20, "n": 3, "seed": 1, "solutes": [{"el": "C", "c": 0.45, "einheit": "wt"}],
                    "fx": {"disl": True, "sf": True}, "slice": "110"}),
        ("xrd", {"item": "p1", "opt": {"phase_ref": "cu", "search": True, "overlay": ["cu"], "quant_ids": ["cu"]}}),
        ("phasen", {"system": "fe-c", "x": 0.35, "T": 726}),
        ("phasen", {"model": {"omega_L": 0}, "x": 35, "T": 1225}),
        ("stahl", {"comp": {"C": 0.18, "Mn": 1.4, "Si": 0.3}, "preheat": {"d": 20, "HD": 5, "Q": 1.5},
                   "hj": {"T1": 600, "t1": 2, "T2": 650}, "carb": {"T": 925, "t": 4, "c0": 0.2, "cs": 0.9}}),
        ("laminat", {"material": "CFK UD", "layup": "[0/±45/90]s", "Nx": 100}),
        ("ermuedung", {"rows": [{"sa": 400, "N": 1e4}, {"sa": 350, "N": 5e4}, {"sa": 300, "N": 2e5}, {"sa": 260, "N": 1e6},
                                {"sa": 240, "N": 1e7, "runout": True}], "mat": {"Rm": 800, "Re": 600}, "model": "goodman",
                       "marin": {"Rm": 800, "d": 10}, "series": [-2, 1, -3, 5, -1, 3, -4, 4, -2]}),
        ("weibull", {"values": ReliabilityTest.X, "B": 100, "size": {"V1": 100, "V2": 1000, "kind1": "3pb", "kind2": "zug"}}),
        ("bruch", {"kq": {"geom": "senb", "P": 12, "B": 20, "W": 40, "a": 20, "Rp": 800, "Pmax": 12.5},
                   "crack": {"KIc": 50, "sigma": 300}}),
        ("haerte", {"method": "HV", "indents": [{"F": 98.07, "d1": 0.300, "d2": 0.302}, {"F": 98.07, "d1": 0.296}],
                    "convert": {"table": "t1", "to": "HRC"}, "grain": {"L": 500, "N": 100, "M": 100},
                    "hp": [{"d": 10, "s": 300}, {"d": 25, "s": 250}, {"d": 50, "s": 220}]}),
        ("korrosion", {"E": E.tolist(), "i": i.tolist(), "iunit": "A", "area": 1, "metal": "Fe", "bv": True}),
        ("kriechen", {"rows": [{"s": 200, "T": 550, "t": 1000}, {"s": 150, "T": 600, "t": 800},
                               {"s": 120, "T": 600, "t": 3000}, {"s": 100, "T": 650, "t": 500},
                               {"s": 80, "T": 650, "t": 2000}], "predict": {"s": 130, "T": 600}}),
        ("struktur", {"material": "c45e-qt", "T": 20, "n": 3, "show": "gefuege"}),
        ("struktur", {"material": "en-aw-6061-t6", "show": "gefuege",
                      "temper": {"steps": [{"name": "Lösungsglühen", "T": 540, "t": 1}, {"name": "Abschrecken", "T": 20, "t": 0, "quench": True},
                                           {"name": "Warmauslagern", "T": 175, "t": 8}, {"name": "Abkühlen", "T": 20, "t": 0}]}}),
    ]
    return ctx, secs


class AllToolsTest(unittest.TestCase):
    def test_every_tool_both_languages_with_known_refs(self):
        ctx, secs = all_cases()
        for lang in ("de", "en"):
            for name, req in secs:
                with self.subTest(tool=name, lang=lang):
                    r = T.run(name, {**req, "lang": lang}, ctx)
                    json.dumps(r, default=lambda o: o.tolist() if hasattr(o, "tolist") else float(o))
                    for ref in r.get("refs") or []:
                        self.assertTrue(RF.known(ref["key"]), ref["key"])

    def test_unknown_tool(self):
        with self.assertRaises(LookupError):
            T.run("gibtsnicht", {}, T.Ctx())


# ============================================================================= Struktur
class StrukturTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from werk import polymer as PY
        from werk import struktur as SK
        cls.SK, cls.PY = SK, PY

    def test_every_material_and_tensile_alloy_has_a_structure(self):
        from labcalc import materials as M
        rows = M.materials()
        have = {m["id"] for m in self.SK.materials("de")}
        self.assertEqual({r["id"] for r in rows} - have, set())
        self.assertTrue(any(r.get("zugversuch") for r in rows))
        self.assertGreaterEqual(len(have), 130)

    def test_all_materials_build_at_room_temperature(self):
        for m in self.SK.materials("en"):
            with self.subTest(material=m["id"]):
                b = self.SK.build(m["id"], 20, "en", n=3)
                self.assertTrue(b["panels"])
                self.assertTrue(b["statements"])
                self.assertLess(len(json.dumps(b)), 400_000)
                for k in b["refs_keys"] + b["q"]:
                    self.assertTrue(RF.known(k), k)
                lo, hi = b["range"]
                self.assertLess(lo, hi)

    def test_views_switch_with_temperature(self):
        cold, hot = self.SK.build("c45e-qt", 20, "en"), self.SK.build("c45e-qt", 850, "en")
        self.assertEqual(cold["panels"][0]["id"], "gefuege")          # Metalle öffnen auf dem Gefüge
        self.assertIn("ferrite", " ".join(p["title"] for p in cold["panels"]).lower())
        self.assertIn("austenite", " ".join(hot["statements"] + [p["title"] for p in hot["panels"]]).lower())
        t6, sol = self.SK.build("en-aw-6061-t6", 20, "en"), self.SK.build("en-aw-6061-t6", 560, "en")
        ids = lambda b: {p["id"] for p in b["panels"]}
        self.assertIn("zelle:mg5si6-bpp", ids(t6))                      # beta'' in T6
        self.assertNotIn("zelle:mg5si6-bpp", ids(sol))                  # dissolved above the solvus
        pe20, pe200 = self.SK.build("pe-hd", 20, "en"), self.SK.build("pe-hd", 200, "en")
        self.assertNotEqual(pe20["statements"], pe200["statements"])
        self.assertIn("melt", " ".join(pe200["statements"]).lower())

    def test_polymer_chain_geometry(self):
        for pid in self.PY.POLY:
            with self.subTest(polymer=pid):
                c = self.PY.chain(pid, 6)
                P = np.array([a[1] for a in c["atoms"]])
                nb = {i: set() for i in range(len(P))}
                for i, j in c["bonds"]:
                    d = float(np.linalg.norm(P[i] - P[j]))
                    self.assertTrue(1.1 < d < 1.9, (i, j, d))
                    nb[i].add(j)
                    nb[j].add(i)
                for i in range(len(P)):                                  # keine Überlappung jenseits von 1-3-Nachbarn
                    for j in range(i + 1, len(P)):
                        if j not in nb[i] and not nb[i] & nb[j]:
                            self.assertGreater(float(np.linalg.norm(P[i] - P[j])), 2.05, (pid, i, j))
        rep = {pid: self.PY.chain(pid, 6)["repeat"] for pid in ("pe", "pp", "ptfe", "pom")}
        self.assertAlmostEqual(rep["pe"], 2.55, delta=0.03)                  # Bunn 1939
        self.assertAlmostEqual(rep["pp"], 6.50 / 3, delta=0.03)              # 3/1-Helix, Natta 1960
        self.assertAlmostEqual(rep["ptfe"], 16.8 / 13, delta=0.02)           # 13/6-Helix
        self.assertAlmostEqual(rep["pom"], 17.39 / 9, delta=0.03)            # 9/5-Helix

    def test_steel_quench_and_temper_path(self):
        pre = {p["id"]: p for p in self.SK.temper_presets("c45e-qt", "en")}
        self.assertEqual(set(pre), {"qt200", "qt400", "qt600"})
        r = self.SK.temper("c45e-qt", pre["qt400"]["steps"], "en")
        labels = [f["label"] for f in r["frames"]]
        self.assertEqual(labels[0], "initial state")
        self.assertIn("quench", labels)
        txt = lambda lab: " ".join(next(f for f in r["frames"] if f["label"] == lab)["statements"]).lower()
        self.assertIn("martensite", txt("quench"))
        self.assertIn("3rd stage", txt("cool"))
        t = [p[0] for p in r["profile"]]
        self.assertEqual(t, sorted(t))
        with self.assertRaises(self.SK.StructError):
            self.SK.temper("c45e-qt", [{"T": 20, "t": 0}] * 9, "en")

    def test_aluminium_ageing_path(self):
        pre = {p["id"]: p for p in self.SK.temper_presets("en-aw-6061-t6", "en")}
        self.assertTrue({"t4", "t6", "t7"} <= set(pre))
        r = self.SK.temper("en-aw-6061-t6", pre["t6"]["steps"], "en")
        st = [" ".join(f["statements"]).lower() for f in r["frames"]]
        self.assertTrue(any("supersaturated" in s for s in st))
        self.assertIn("peak", st[-1])
        self.assertEqual(self.SK.temper_presets("pe-hd", "en"), [])

    def test_step_names_follow_the_language(self):
        steps = [{"name": "Austenitisieren", "T": 820, "t": 0.5}, {"name": "Abschrecken", "T": 20, "t": 0, "quench": True},
                 {"name": "Mein Schritt", "T": 300, "t": 1}]
        r = self.SK.temper("c45e-qt", steps, "en")
        self.assertEqual([s["name"] for s in r["steps"]], ["austenitise", "quench", "Mein Schritt"])

    def test_sketches_are_compact(self):
        b = self.SK.build("c45e-qt", 20, "de")
        sk = next(p for p in b["panels"] if p["kind"] == "sketch")["sketch"]
        self.assertLess(len(json.dumps(sk)), 150_000)
        kinds = {it["t"] for it in sk["items"]}
        self.assertIn("hatch", kinds)
        self.assertTrue(self.SK.hatch_lines(next(it for it in sk["items"] if it["t"] == "hatch")))

    def test_tool_errors(self):
        with self.assertRaises(T.ToolError):
            T.run("struktur", {}, T.Ctx())
        with self.assertRaises(T.ToolError):
            T.run("struktur", {"material": "c45e-qt", "n": 9}, T.Ctx())
        with self.assertRaises(self.SK.StructError):
            T.run("struktur", {"material": "gibtsnicht"}, T.Ctx())

    def test_report_figures_render(self):
        from werk import charts as CH
        for mid in ("pe-ld", "al2o3-999", "kalk-natron-glas"):
            for p in self.SK.build(mid, 20, "en", n=3)["panels"]:
                CH.close(CH.fig_panel(p, "en"))
        r = self.SK.temper("c45e-qt", self.SK.temper_presets("c45e-qt", "en")[0]["steps"], "en")
        CH.close(CH.fig_temper_path(r, "en"))
        CH.close(CH.fig_temper_frames(r, "en", "gefuege"))


# ============================================================================= Bericht
class BundleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ctx, secs = all_cases()
        x, y = cu_pattern()
        raw = "\n".join(f"{a:.3f} {b:.2f}" for a, b in zip(x, y)).encode()
        ctx.items["p1"]["obj"] = IO.load(raw, "cu.xy")
        cls.ctx, cls.raw = ctx, raw
        cls.req = {"sections": [{"tool": n, "req": r} for n, r in secs], "lang": "de",
                   "files": [{"id": "p1", "name": "cu.xy", "kind": "xrd", "file": "p1/cu.xy"},
                             {"id": "t1", "name": "conv.csv", "kind": "hardtable", "file": "t1/conv.csv"}]}
        cls.files = {"p1/cu.xy": raw, "t1/conv.csv": ctx.items["t1"]["obj"].encode()}
        cls.b = B.build(cls.req, ctx, cls.files)

    def test_kinds_and_citations_resolve(self):
        kinds = {}
        for it in self.b["items"]:
            kinds[it["kind"]] = kinds.get(it["kind"], 0) + 1
        for k in ("figure", "table", "values", "citation", "text", "data"):
            self.assertIn(k, kinds)
        files = {k: base64.b64decode(v).decode("utf-8", "replace") for k, v in self.b["files"].items()}
        bib = files["refs.bib"]
        keys = set(re.findall(r"@\w+\{([^,]+),", bib))
        used = set()
        for name, txt in files.items():
            if name.endswith(".tex"):
                for grp in re.findall(r"\\cite[pt]?\{([^}]+)\}", txt):
                    used.update(k.strip() for k in grp.split(","))
        self.assertTrue(used)
        self.assertEqual(used - keys, set())
        self.assertIn("key = {cu.xy}", bib)                                  # Messdatei mit Sortierschlüssel
        own = [k for k in keys if k.startswith("own-")]                      # eigene Quelle: Eintrag mit URL, zitiert
        self.assertEqual(len(own), 1)
        self.assertIn(own[0], used)
        self.assertIn("url = {https://example.org/ds.pdf}", bib)
        tex = "".join(v for k, v in files.items() if k.endswith(".tex"))
        self.assertIn("ohne Quellenangabe", tex)                             # Punkt ohne Quelle gekennzeichnet
        self.assertIn("Mein Al", tex)

    def test_labels_and_methods(self):
        files = {k: base64.b64decode(v).decode("utf-8", "replace") for k, v in self.b["files"].items()}
        meth = files.get("text-methodik.tex", "")
        self.assertIn("schematisch", meth.lower())                           # schematische Diagramme gekennzeichnet
        self.assertIn("berechnet", meth.lower())
        self.assertNotIn("\\text{", "".join(files[k] for k in files if k.endswith(".tex")))
        for k, v in files.items():
            if k.endswith(".tex"):
                self.assertNotIn("\\ce{", v, k)
                self.assertNotIn("\\tfrac", v, k)

    def test_english_and_selected_parts(self):
        b = B.build({**self.req, "lang": "en", "include": {"figures": False, "data": False}}, self.ctx, self.files)
        kinds = {it["kind"] for it in b["items"]}
        self.assertNotIn("figure", kinds)
        self.assertNotIn("data", kinds)
        self.assertIn("table", kinds)
        self.assertTrue(b["title"].startswith("Materials"))

    def test_used_items(self):
        self.assertEqual(sorted(B.used_items(self.req["sections"])), ["p1", "t1"])


# ============================================================================= Server
class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from werk import server as S
        cls.S = S
        cls.tmp = TemporaryDirectory()
        S.STATE = S.State(Path(cls.tmp.name))
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), S.Handler)
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.tmp.cleanup()

    def post(self, path, body=None, raw=None, origin=None):
        data = raw if raw is not None else json.dumps(body or {}).encode()
        req = urllib.request.Request(self.base + path, data=data, method="POST")
        req.add_header("Content-Type", "application/octet-stream" if raw is not None else "application/json")
        if origin:
            req.add_header("Origin", origin)
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def get(self, path):
        with urllib.request.urlopen(self.base + path, timeout=60) as r:
            return r.status, r.read()

    def test_meta_and_page(self):
        code, body = self.get("/api/meta")
        m = json.loads(body)
        self.assertEqual(code, 200)
        self.assertTrue(m["systems"])
        self.assertTrue(m["plies"])
        code, page = self.get("/")
        self.assertIn(b"<title>", page)

    def test_flow_load_tool_bundle_rebuild(self):
        x, y = cu_pattern()
        raw = "\n".join(f"{a:.3f} {b:.2f}" for a, b in zip(x, y)).encode()
        code, it = self.post("/api/load?name=cu.xy", raw=raw)
        self.assertEqual(code, 200, it)
        self.assertEqual(it["kind"], "xrd")
        code, r = self.post("/api/tool/xrd", {"item": it["id"], "opt": {"search": True}})
        self.assertEqual(code, 200, r)
        self.assertEqual(len(r["peaks"]), 6)
        secs = [{"tool": "xrd", "req": {"item": it["id"], "opt": {"overlay": ["cu"]}}},
                {"tool": "bruch", "req": {"kq": {"geom": "senb", "P": 12, "B": 20, "W": 40, "a": 20}}}]
        code, b = self.post("/api/bundle", {"sections": secs, "lang": "de"})
        self.assertEqual(code, 200, b)
        n = len(b["items"])
        self.assertTrue(any(f.endswith("cu.xy") for f in b["source"]["files"]))
        for f in b["source"]["files"]:                                      # Regel des Hubs (server/lab.js save)
            self.assertRegex(f, r'^[^\\/:*?"<>|]{1,120}$')
            self.assertNotIn("..", f)
        code, b2 = self.post("/api/bundle/rebuild", {"source": b["source"], "lang": "en"})
        self.assertEqual(code, 200, b2)
        self.assertEqual(len(b2["items"]), n)
        self.assertEqual(b2["lang"], "en")

    def test_bad_files_and_origin(self):
        code, j = self.post("/api/load?name=neu.raw", raw=b"RAW4.00" + bytes(900))
        self.assertEqual(code, 400)
        self.assertIn("Version 4", j["error"])
        code, j = self.post("/api/load?name=x.bin&kind=exe", raw=b"0")
        self.assertEqual(code, 400)
        code, j = self.post("/api/tool/bruch", {"kq": {"geom": "senb", "P": 12, "B": 20, "W": 40, "a": 20}},
                            origin="https://example.com")
        self.assertEqual(code, 403)
        code, j = self.post("/api/tool/weibull", {"values": [1, 2]})
        self.assertEqual(code, 400)
        self.assertTrue(j["error"])

    def test_cif_load_gives_phase(self):
        cif = ("data_cu\n_cell_length_a 3.6149\n_cell_length_b 3.6149\n_cell_length_c 3.6149\n_cell_angle_alpha 90\n"
               "_cell_angle_beta 90\n_cell_angle_gamma 90\n_symmetry_space_group_name_H-M 'P 1'\nloop_\n_atom_site_label\n"
               "_atom_site_fract_x\n_atom_site_fract_y\n_atom_site_fract_z\nCu1 0 0 0\nCu2 0.5 0.5 0\nCu3 0.5 0 0.5\nCu4 0 0.5 0.5\n")
        code, it = self.post("/api/load?name=cu.cif", raw=cif.encode())
        self.assertEqual(code, 200, it)
        self.assertEqual(it["system"], "cubic")
        code, r = self.post("/api/tool/kristall", {"phase": it["phase_id"]})
        self.assertEqual(code, 200, r)
        self.assertEqual([L["hkl"] for L in r["lines"]][:2], ["111", "200"])


class UncertaintyViewsTest(unittest.TestCase):
    """Messunsicherheit in Bruch, Härte, Stahl; Erklärung und Quellen je Ansicht."""
    KQ = {"geom": "senb", "P": 12, "B": 25, "W": 50, "a": 25, "S": 200}

    def test_kq_budget_and_compare(self):
        req = {"kq": self.KQ, "unc": {"bruch.kq.P": {"parts": [{"kind": "rel", "pct": 1}]},
                                      "bruch.kq.a": {"parts": [{"kind": "limits", "a": 0.1}]}}}
        r = T.run("bruch", req, T.Ctx())
        u = r["unc"]["kq"]
        self.assertAlmostEqual(u["value"], r["kq"]["K"], places=6)
        self.assertGreater(u["U"], 0)
        self.assertEqual({b["name"] for b in u["budget"] if not b["exact"]}, {"P", "a"})
        self.assertIn("jcgm100", u["refs"])
        r2 = T.run("bruch", {**req, "unc_compare": "kq"}, T.Ctx())
        self.assertEqual(set(r2["unc"]["kq"]["compare"]), {"gum", "mc", "gauss", "worst"})
        self.assertNotIn("unc", T.run("bruch", {"kq": self.KQ}, T.Ctx()))      # ohne Angabe keine Unsicherheit

    def test_hardness_repeats_alone_give_type_a(self):
        req = {"method": "HV", "indents": [{"F": 98.07, "d1": 0.43}, {"F": 98.07, "d1": 0.44}, {"F": 98.07, "d1": 0.435}]}
        u = T.run("haerte", req, T.Ctx())["unc"]["haerte"]
        row = next(b for b in u["budget"] if b["name"] == "Hbar")
        self.assertEqual(row["type"], "A")
        self.assertEqual(row["dof"], 2)

    def test_steel_drops_results_without_uncertain_input(self):
        r = T.run("stahl", {"comp": {"C": 0.18, "Mn": 1.4, "Si": 0.3},
                            "unc": {"stahl.comp.C": {"parts": [{"kind": "limits", "a": 0.02}]}}}, T.Ctx())
        self.assertIn("CE", r["unc"])
        self.assertNotIn("Ac1", r["unc"])                 # Ac1 hängt nicht von C ab

    def test_report_has_budget_and_cites_gum(self):
        req = {"kq": self.KQ, "unc": {"bruch.kq.P": {"parts": [{"kind": "rel", "pct": 1}]}}}
        b = B.build({"sections": [{"tool": "bruch", "req": req}], "lang": "en"}, T.Ctx(), {})
        ids = {it.get("id") for it in b["items"]}
        self.assertIn("bruch-kq-budget", ids)
        files = {k: base64.b64decode(v).decode("utf-8", "replace") for k, v in b["files"].items()}
        self.assertIn("unc-jcgm100", files["refs.bib"])
        self.assertIn("$K_{Q}$", files["text-methodik.tex"])

    def test_every_view_has_compendium_entry_and_its_sources(self):
        cases = {"bruch": {"kq": self.KQ},
                 "haerte": {"method": "HV", "indents": [{"F": 98.07, "d1": 0.43}]},
                 "weibull": {"values": [300, 320, 340, 355, 370, 390]}}
        for tool, req in cases.items():
            r = T.run(tool, req, T.Ctx())
            vi = r.get("views_info")
            self.assertTrue(vi, tool)
            have = {q["key"] for q in r.get("refs") or []}
            for view, e in vi.items():
                self.assertTrue(e["entry"].startswith("tool:" + tool), (tool, view))
                self.assertNotIn("more", e)
                self.assertLessEqual(set(e.get("keys") or []), have, (tool, view))


if __name__ == "__main__":
    unittest.main()
