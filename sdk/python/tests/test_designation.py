"""Werkstoffbezeichnungs-Decoder (labcalc.designation): bekannte Antworten, ganze Werkstoffdatenbank, Quellen, Englisch."""
import unittest

from labcalc import designation as D
from labcalc import materials as M
from labcalc import sources as SRC


def one(text, lang="de", hint=None):
    """Genau eine erkannte Bezeichnung, nichts Unerklärtes."""
    d = D.decode(text, lang, hint=hint)
    assert d["unknown"] == [], (text, d["unknown"])
    assert len(d["found"]) == 1, (text, [f["code"] for f in d["found"]])
    return d["found"][0]


def part(f, code):
    for p in f["parts"]:
        if p["code"] == code:
            return p["meaning"]
    raise AssertionError(f"Teil {code!r} fehlt in {f['code']}: {[p['code'] for p in f['parts']]}")


class Aluminium(unittest.TestCase):
    def test_1050a(self):
        f = one("EN AW-1050A")
        self.assertEqual([p["code"] for p in f["parts"]][:4], ["EN", "A", "W", "1050"])
        self.assertIn("99,50", part(f, "1050"))
        self.assertEqual(f["parts"][4]["code"], "A")                 # zweites „A“: Suffix hinter der Nummer
        self.assertIn("nationale Variante", f["parts"][4]["meaning"])
        self.assertEqual(f["composition"], {"Al": "≥ 99,50"})
        self.assertIn("Al99,5", f["summary"])

    def test_5052_h38(self):
        f = one("EN AW-5052-H38")
        self.assertEqual(f["system"], "EN 573 / EN 515")
        self.assertEqual(f["family"], "Aluminium-Knetlegierung")
        self.assertIn("Magnesium", part(f, "5052"))
        self.assertIn("stabilisiert", part(f, "H38"))
        self.assertIn("8 = voll hart", part(f, "H38"))
        self.assertEqual(f["composition"], {"Mg": "2,2–2,8", "Cr": "0,15–0,35"})
        self.assertIn("en-573-1", f["refs"])
        self.assertIn("en-515", f["refs"])

    def test_6061_t6(self):
        f = one("EN AW-6061-T6")
        self.assertIn("Silicium", part(f, "6061"))
        self.assertEqual(part(f, "T6"), "lösungsgeglüht und warmausgelagert")
        self.assertEqual(f["composition"]["Mg"], "0,8–1,2")

    def test_7075_t651(self):
        f = one("EN AW-7075-T651")
        self.assertIn("warmausgelagert", part(f, "T6"))
        self.assertIn("Recken", part(f, "51"))
        self.assertIn("Zink", part(f, "7075"))

    def test_5083_two_tempers(self):
        f = one("EN AW-5083-O/H111")
        self.assertIn("weichgeglüht", part(f, "O"))
        self.assertIn("geringfügig kaltverfestigt", part(f, "H111"))
        self.assertIn("beider Zustände", part(f, "/"))

    def test_chemical_symbol_form(self):
        f = one("EN AW-Al Mg2,5")
        self.assertIn("EN AW-5052", f["summary"])
        self.assertIn("2,5", part(f, "Mg2,5"))
        f = one("AlMg4,5Mn0,7 O")
        self.assertIn("5083", f["summary"])
        f = one("AlCu4MgSi(A) T4")
        self.assertIn("2017A", f["summary"])

    def test_bare_number_with_temper(self):
        self.assertIn("5052", one("5052-H32")["summary"])
        self.assertIn("8011A", one("8011A-O")["summary"])

    def test_cast(self):
        f = one("EN AC-42100")
        self.assertEqual(f["system"], "EN 1780-1")
        self.assertIn("Silicium", part(f, "42100"))


class Steel(unittest.TestCase):
    def test_s235jr(self):
        f = one("S235JR")
        self.assertIn("235 MPa", part(f, "235"))
        self.assertEqual(part(f, "JR"), "Kerbschlagarbeit mindestens 27 J bei +20 °C")
        self.assertIn("1.0038", f["summary"])

    def test_s355j2(self):
        f = one("S355J2")
        self.assertEqual(part(f, "J2"), "Kerbschlagarbeit mindestens 27 J bei −20 °C")
        self.assertIn("1.0577", f["summary"])

    def test_s460n(self):
        f = one("S460N")
        self.assertIn("normalgeglüht", part(f, "N"))

    def test_dc04(self):
        f = one("DC04")
        self.assertEqual(part(f, "C"), "kaltgewalzt")
        self.assertIn("Tiefziehgüte", part(f, "04"))
        self.assertIn("en-10130", f["refs"])

    def test_c45e_qt(self):
        f = one("C45E +QT")
        self.assertIn("0,45 %", part(f, "45"))
        self.assertIn("Schwefel", part(f, "E"))
        self.assertIn("vergütet", part(f, "+QT"))
        self.assertEqual(f["composition"]["C"], "0,42–0,50")

    def test_42crmo4(self):
        f = one("42CrMo4")
        self.assertIn("0,42 %", part(f, "42"))
        self.assertIn("4 ÷ 4 ≈ 1 %", part(f, "4"))
        self.assertIn("Molybdän", part(f, "Mo"))
        self.assertEqual(f["composition"]["Cr"], "0,90–1,20")
        self.assertIn("1.7225", f["summary"])

    def test_x5crni18_10(self):
        f = one("X5CrNi18-10")
        self.assertIn("nichtrostend", f["family"])
        self.assertIn("Chrom etwa 18 %", part(f, "18"))
        self.assertIn("Nickel etwa 10 %", part(f, "10"))
        self.assertEqual(f["composition"]["Cr"], "17,5–19,5")

    def test_number_1_4301(self):
        f = one("1.4301")
        self.assertIn("nichtrostende Stähle mit ≥ 2,5 % Ni, ohne Mo", part(f, "43"))
        self.assertIn("X5CrNi18-10", f["summary"])

    def test_number_1_4571(self):
        f = one("1.4571")
        self.assertIn("Sonderzusätzen", part(f, "45"))
        self.assertIn("X6CrNiMoTi17-12-2", f["summary"])

    def test_number_and_name_together(self):
        d = D.decode("1.4301 (X5CrNi18-10)")
        self.assertEqual([f["code"] for f in d["found"]], ["1.4301", "X5CrNi18-10"])
        self.assertEqual(d["unknown"], [])

    def test_high_speed(self):
        f = one("HS6-5-2-5")
        self.assertIn("Wolfram etwa 6 %", part(f, "6"))

    def test_aisi_4340(self):
        f = one("AISI 4340")
        self.assertIn("Nickel-Chrom-Molybdän", part(f, "43"))
        self.assertIn("0,4 %", part(f, "40"))
        self.assertEqual(f["composition"]["Ni"], "1,65–2,00")

    def test_aisi_316l(self):
        f = one("316L")
        self.assertIn("1.4404", f["summary"])
        self.assertIn("C ≤ 0,03 %", part(f, "L"))

    def test_old_names(self):
        self.assertIn("S235JR", one("St37-2")["summary"])
        self.assertIn("C45E", one("Ck45 +N")["summary"])

    def test_bare_four_digit_needs_hint(self):
        d = D.decode("1020")
        self.assertEqual(d["found"], [])
        self.assertEqual(d["unknown"], ["1020"])
        self.assertIn("mehrdeutig", d["summary"])
        f = one("1020", hint="Stahl")
        self.assertIn("Kohlenstoffstahl", f["summary"])
        self.assertIn("1020", one("1020", hint="Aluminium")["summary"])


class CastIronCopper(unittest.TestCase):
    def test_gjl_250(self):
        f = one("EN-GJL-250")
        self.assertIn("Lamellengraphit", part(f, "L"))
        self.assertEqual(part(f, "250"), "Mindestzugfestigkeit 250 MPa")

    def test_gjs_400_15(self):
        f = one("EN-GJS-400-15")
        self.assertIn("Kugelgraphit", part(f, "S"))
        self.assertEqual(part(f, "15"), "Mindestbruchdehnung 15 %")
        self.assertIn("EN-GJL-250", one("GG-25")["summary"])

    def test_cu_etp_r220(self):
        f = one("Cu-ETP R220")
        self.assertIn("Electrolytic Tough Pitch", part(f, "ETP"))
        self.assertIn("Mindestzugfestigkeit 220 MPa", part(f, "R220"))
        self.assertIn("CW004A", part(f, "≙ CW004A"))

    def test_cuzn37_r300(self):
        f = one("CuZn37 R300")
        self.assertTrue(f["family"].startswith("Messing"))
        self.assertIn("37 %", part(f, "Zn37"))
        self.assertEqual(f["composition"], {"Cu": "62,0–64,0", "Zn": "Rest"})

    def test_cusn6_r550(self):
        f = one("CuSn6 R550")
        self.assertTrue(f["family"].startswith("Zinnbronze"))
        self.assertIn("550 MPa", part(f, "R550"))

    def test_cw_number(self):
        f = one("CW508L")
        self.assertIn("Kupfer-Zink-Zweistofflegierungen", part(f, "L"))
        self.assertIn("CuZn37", f["summary"])


class OtherMetals(unittest.TestCase):
    def test_titan_grade_2(self):
        f = one("Grade 2")
        self.assertIn("Rm ≥ 345 MPa", f["summary"])
        self.assertEqual(f["family"], "Reintitan")
        self.assertIn("3.7035", one("Titan Grade 2")["summary"] + str(one("Titan Grade 2")["parts"]))

    def test_ti64(self):
        f = one("Ti-6Al-4V")
        self.assertIn("Grade 5", f["summary"])
        self.assertEqual(f["composition"]["Al"], "5,5–6,75")

    def test_az31b_h24(self):
        f = one("AZ31B-H24")
        self.assertIn("Aluminium", part(f, "A"))
        self.assertIn("Zink", part(f, "Z"))
        self.assertIn("halbhart", part(f, "H24"))
        self.assertEqual(f["composition"]["Al"], "2,5–3,5")

    def test_inconel_718(self):
        f = one("Inconel 718")
        self.assertIn("N07718", f["summary"])
        self.assertIn("2.4668", f["summary"])
        self.assertIn("Special Metals", part(f, "Inconel"))
        self.assertEqual(f["composition"]["Nb+Ta"], "4,75–5,50")

    def test_nickel_200_and_uns(self):
        self.assertIn("N02200", one("Nickel 200")["summary"])
        f = one("UNS N06625")
        self.assertIn("Nickel", part(f, "N"))
        self.assertIn("Inconel 625", f["summary"])


class Polymers(unittest.TestCase):
    def test_pa66_gf30(self):
        f = one("PA66-GF30")
        self.assertIn("Hexamethylendiamin", part(f, "66"))
        self.assertIn("Glasfasern, 30 %", part(f, "GF30"))
        self.assertIn("iso-1043-2", f["refs"])

    def test_pe_hd(self):
        self.assertIn("hohe Dichte", part(one("PE-HD"), "HD"))

    def test_pvc_u(self):
        self.assertIn("weichmacherfrei", part(one("PVC-U"), "U"))

    def test_pp_h(self):
        self.assertIn("Homopolymer", part(one("PP-H"), "H"))

    def test_epdm(self):
        f = one("EPDM")
        self.assertIn("Ethylen-Propylen-Dien", part(f, "EPDM"))
        self.assertIn("gesättigte", part(f, "M"))

    def test_vmq(self):
        self.assertIn("Silicium und Sauerstoff", part(one("VMQ"), "Q"))

    def test_nbr_shore(self):
        d = D.decode("NBR (70 Shore A)")
        self.assertEqual(d["unknown"], [])
        self.assertEqual(d["found"][0]["code"], "NBR")
        self.assertIn("Shore-Härte 70", d["qualifiers"][0]["meaning"])

    def test_tpu(self):
        self.assertIn("Polyurethan", one("TPU")["summary"])

    def test_dry_and_conditioned(self):
        d = D.decode("PA6 trocken")
        self.assertEqual(d["qualifiers"][0]["code"], "trocken")
        d = D.decode("PA6 konditioniert")
        self.assertIn("23 °C", d["qualifiers"][0]["meaning"])
        self.assertEqual(d["qualifiers"][0]["refs"], ["iso-291", "iso-1110"])

    def test_film(self):
        d = D.decode("PET-Folie (BOPET), längs")
        self.assertEqual(d["unknown"], [])
        self.assertEqual([q["code"] for q in d["qualifiers"]], ["Folie", "BOPET", "längs"])


class CompositesAndPlain(unittest.TestCase):
    def test_cfrp_ud(self):
        d = D.decode("CFK-UD AS4/3501-6")
        self.assertEqual([f["code"] for f in d["found"]], ["CFK-UD", "AS4/3501-6"])
        self.assertIn("Hexcel", d["found"][1]["parts"][0]["meaning"])

    def test_plain_names(self):
        for text in ("Kupfer (rein)", "Beton", "Fichte"):
            d = D.decode(text)
            self.assertEqual(d["unknown"], [], text)
            self.assertTrue(d["found"][0].get("plain"), text)
            self.assertIn("keine Normbezeichnung", d["found"][0]["system"])

    def test_unknown_is_reported_not_guessed(self):
        d = D.decode("S235JR Quatsch")
        self.assertEqual(d["unknown"], ["Quatsch"])
        self.assertIn("Nicht erklärt", d["summary"])
        self.assertIn("Quatsch", d["summary"])
        d = D.decode("EN AW-5052-H99X")
        self.assertTrue(d["unknown"])
        self.assertEqual(D.decode("")["found"], [])


class English(unittest.TestCase):
    def test_5052_en(self):
        f = one("EN AW-5052-H38", "en")
        self.assertEqual(f["family"], "wrought aluminium alloy")
        self.assertEqual(part(f, "W"), "wrought product")
        self.assertIn("8 = full hard", part(f, "H38"))
        self.assertEqual(f["composition"], {"Mg": "2.2–2.8", "Cr": "0.15–0.35"})

    def test_steel_en(self):
        f = one("S355J2", "en")
        self.assertEqual(part(f, "J2"), "impact energy at least 27 J at -20 °C")
        self.assertIn("4 ÷ 4 ≈ 1 %", part(one("42CrMo4", "en"), "4"))

    def test_qualifiers_en(self):
        d = D.decode("PA6, dry", "en")
        self.assertIn("dry as moulded", d["qualifiers"][0]["meaning"])
        d = D.decode("Cu-ETP R220 (weich)", "en")
        self.assertIn("annealed", d["qualifiers"][0]["meaning"])
        self.assertIn("minimum tensile strength 220 MPa", d["found"][0]["summary"])

    def test_plain_en(self):
        d = D.decode("Concrete", "en")
        self.assertIn("plain name", d["found"][0]["system"])


# Werkstoffe, deren Name bzw. Aliase sich nicht vollständig erklären lassen, mit Begründung. Derzeit keine.
EXCEPTIONS: dict[str, str] = {}


class WholeDatabase(unittest.TestCase):
    def test_every_material_name_decodes(self):
        rows = M.materials()
        self.assertEqual(len(rows), 136)
        for r in rows:
            for lang, name in (("de", r["name"]), ("en", r.get("name_en") or r["name"])):
                d = D.decode(name, lang, hint=r.get("familie"))
                if r["id"] in EXCEPTIONS:
                    continue
                with self.subTest(material=r["id"], lang=lang):
                    self.assertTrue(d["found"], name)
                    self.assertEqual(d["unknown"], [], name)
                    self.assertTrue(d["summary"])

    def test_metals_polymers_elastomers_have_designation(self):
        for r in M.materials():
            if r["klasse"] not in ("metall", "polymer") or r["id"] in EXCEPTIONS:
                continue
            d = D.decode(r["name"], hint=r.get("familie"))
            with self.subTest(material=r["id"]):
                self.assertTrue(any(f["parts"] for f in d["found"]))
                self.assertEqual(d["unknown"], [])

    def test_decode_material_with_aliases(self):
        for r in M.materials():
            for lang in ("de", "en"):
                d = D.decode_material(r["id"], lang)
                if r["id"] in EXCEPTIONS:
                    continue
                with self.subTest(material=r["id"], lang=lang):
                    self.assertEqual(d["unknown"], [])
                    self.assertEqual(len(d["aliases"]), len(r.get("aliase") or []))

    def test_decode_material_merges_aliases(self):
        d = D.decode_material("1.4301 (X5CrNi18-10)")
        codes = [f["code"] for f in d["found"]]
        self.assertEqual(codes[:2], ["1.4301", "X5CrNi18-10"])
        self.assertIn("AISI 304", codes)
        self.assertEqual(next(f for f in d["found"] if f["code"] == "V2A")["from"], "V2A")
        self.assertEqual(d["material"]["familie"], "Edelstahl")
        d = D.decode_material("aisi-1020-warmgewalzt")
        self.assertIn("1020", [f["code"] for f in d["found"]])


class Sources(unittest.TestCase):
    def test_new_records(self):
        for key in D.REF_KEYS:
            with self.subTest(key=key):
                r = SRC.REFS[key]
                self.assertEqual(r["note"], "Angaben nicht am Original geprüft")
                for field in ("type", "authors", "title", "container", "year"):
                    self.assertTrue(r.get(field), field)

    def test_every_cited_ref_exists(self):
        texts = [r["name"] for r in M.materials()] + [a for r in M.materials() for a in (r.get("aliase") or [])]
        texts += ["EN AC-42100", "HS6-5-2-5", "UNS N06625", "PA6 konditioniert", "NBR (70 Shore A)", "+QT", "B500B",
                  "Y1770C", "M400-50A", "HC340LA", "DX51D", "P265GH", "R260Mn", "GJMW-350-4"]
        used = set()
        for t in texts:
            d = D.decode(t)
            for f in d["found"]:
                used.update(f["refs"])
            for q in d["qualifiers"]:
                used.update(q.get("refs") or [])
        for _, _, _, refs in D.SYSTEMS:
            used.update(refs)
        self.assertFalse(used - set(SRC.REFS), sorted(used - set(SRC.REFS)))


if __name__ == "__main__":
    unittest.main()
