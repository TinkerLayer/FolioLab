"""Werkstoffbezeichnungen im Klartext: regelbasierter Decoder für genormte Kurzzeichen und Nummern.

``decode("EN AW-5052-H38")`` zerlegt eine Bezeichnung in ihre Bestandteile und erklärt jeden nach der Norm, die ihn
festlegt: Aluminium (EN 573, EN 515, EN 1780-1), Stahl (EN 10027-1/-2, SAE J403/J404/J405, alte DIN-Namen),
Gusseisen (EN 1560), Kupfer (ISO 1190-1, EN 1412, EN 1173), Titan (ASTM B265/B348), Magnesium (ASTM B275/B296),
Nickel (UNS, DIN 17740/17742, Handelsnamen), Kunststoffe und Elastomere (ISO 1043-1/-2, ISO 1629, ISO 18064),
Faserverbunde (CFK/GFK/AFK, Faser/Matrix). Klartextnamen („Kupfer (rein)“, „Beton“) werden als solche erkannt.

Es wird nicht geraten: was keine Regel erklärt, steht in ``unknown`` und die Zusammenfassung sagt es. Mehrdeutige
Kurzformen (eine nackte vierstellige Zahl kann Aluminium oder SAE-Stahl sein) werden nur mit ``hint`` (Werkstofffamilie)
aufgelöst. Die Normangaben sind aus Sekundärwissen zusammengestellt; die Quellendatensätze in ``sources.REFS``
tragen deshalb den Hinweis „Angaben nicht am Original geprüft“.
"""
from __future__ import annotations

import re
import unicodedata

__all__ = ["decode", "decode_material", "SYSTEMS", "REF_KEYS"]

# Quellendatensätze, die für diesen Decoder in sources.REFS ergänzt wurden (alle „Angaben nicht am Original geprüft“)
REF_KEYS = ("en-573-1", "en-573-2", "en-573-3", "en-515", "en-1780-1", "en-10027-1", "en-10027-2", "en-10025-2", "en-10130",
            "en-10083-2", "en-10083-3", "en-10088-1", "en-1560", "iso-1190-1", "en-1412", "en-1173", "astm-b265", "astm-b348",
            "astm-b275", "astm-b296", "astm-b90", "astm-e527", "astm-b162", "astm-b443", "astm-b637", "sae-j403", "sae-j404",
            "sae-j405", "iso-1043-1", "iso-1043-2", "iso-1629", "iso-18064", "iso-868", "iso-291", "iso-1110", "din-17007-4",
            "din-17740", "din-17742", "din-17100", "din-1623-1", "din-17200", "din-1691", "din-1693-1", "din-17660")


# ============================================================================ Grunddaten
EL = {
    "Ag": ("Silber", "silver"), "Al": ("Aluminium", "aluminium"), "As": ("Arsen", "arsenic"), "Au": ("Gold", "gold"),
    "B": ("Bor", "boron"), "Be": ("Beryllium", "beryllium"), "Bi": ("Bismut", "bismuth"),
    "C": ("Kohlenstoff", "carbon"), "Ca": ("Calcium", "calcium"), "Cd": ("Cadmium", "cadmium"), "Ce": ("Cer", "cerium"),
    "Co": ("Cobalt", "cobalt"), "Cr": ("Chrom", "chromium"), "Cu": ("Kupfer", "copper"), "Fe": ("Eisen", "iron"),
    "Ga": ("Gallium", "gallium"), "Ge": ("Germanium", "germanium"), "Li": ("Lithium", "lithium"),
    "Mg": ("Magnesium", "magnesium"), "Mn": ("Mangan", "manganese"), "Mo": ("Molybdän", "molybdenum"),
    "N": ("Stickstoff", "nitrogen"), "Nb": ("Niob", "niobium"), "Ni": ("Nickel", "nickel"), "O": ("Sauerstoff", "oxygen"),
    "P": ("Phosphor", "phosphorus"), "Pb": ("Blei", "lead"), "Pd": ("Palladium", "palladium"), "Pt": ("Platin", "platinum"),
    "S": ("Schwefel", "sulphur"), "Sb": ("Antimon", "antimony"), "Sc": ("Scandium", "scandium"),
    "Si": ("Silicium", "silicon"), "Sn": ("Zinn", "tin"), "Sr": ("Strontium", "strontium"), "Ta": ("Tantal", "tantalum"),
    "Te": ("Tellur", "tellurium"), "Th": ("Thorium", "thorium"), "Ti": ("Titan", "titanium"), "V": ("Vanadium", "vanadium"),
    "W": ("Wolfram", "tungsten"), "Y": ("Yttrium", "yttrium"), "Zn": ("Zink", "zinc"), "Zr": ("Zirconium", "zirconium"),
}

# Quellenschlüssel (sources.REFS)
R_AL = ["en-573-1"]
R_AL2 = ["en-573-2"]
R_AL3 = ["en-573-3"]
R_T = ["en-515"]

SYSTEMS = [
    ("aluminium", "Aluminium: EN 573-1/-2/-3, Zustände EN 515, Guss EN 1780-1",
     "Aluminium: EN 573-1/-2/-3, tempers EN 515, castings EN 1780-1", ["en-573-1", "en-573-2", "en-573-3", "en-515", "en-1780-1"]),
    ("stahl", "Stahl: Kurznamen EN 10027-1, Werkstoffnummern EN 10027-2, SAE/AISI, alte DIN-Namen",
     "Steel: names EN 10027-1, numbers EN 10027-2, SAE/AISI, former DIN names",
     ["en-10027-1", "en-10027-2", "sae-j403", "sae-j404", "sae-j405"]),
    ("gusseisen", "Gusseisen: EN 1560", "Cast iron: EN 1560", ["en-1560"]),
    ("kupfer", "Kupfer: ISO 1190-1, Werkstoffnummern EN 1412, Zustände EN 1173",
     "Copper: ISO 1190-1, numbers EN 1412, conditions EN 1173", ["iso-1190-1", "en-1412", "en-1173"]),
    ("titan", "Titan: ASTM B265/B348 Grades, Elementschreibweise Ti-6Al-4V",
     "Titanium: ASTM B265/B348 grades, element form Ti-6Al-4V", ["astm-b265", "astm-b348"]),
    ("magnesium", "Magnesium: ASTM B275 Kennbuchstaben, Zustände ASTM B296",
     "Magnesium: ASTM B275 code letters, tempers ASTM B296", ["astm-b275", "astm-b296"]),
    ("nickel", "Nickel: UNS (ASTM E527), DIN 17740/17742, Handelsnamen",
     "Nickel: UNS (ASTM E527), DIN 17740/17742, trade names", ["astm-e527", "din-17740", "din-17742"]),
    ("kunststoff", "Kunststoffe: ISO 1043-1 und -2", "Plastics: ISO 1043-1 and -2", ["iso-1043-1", "iso-1043-2"]),
    ("elastomer", "Elastomere: ISO 1629, TPE ISO 18064, Shore-Härte ISO 868",
     "Elastomers: ISO 1629, TPE ISO 18064, Shore hardness ISO 868", ["iso-1629", "iso-18064", "iso-868"]),
    ("verbund", "Faserverbunde: CFK/GFK/AFK, Faser/Matrix-Systeme", "Composites: CFRP/GFRP/AFRP, fibre/matrix systems",
     ["daniel2006"]),
]


class _Ctx:
    def __init__(self, lang: str, hint: str | None):
        self.lang = lang
        self.hint = hint

    def t(self, de: str, en: str) -> str:
        return en if self.lang == "en" else de

    def p(self, code: str, de: str, en: str) -> dict:
        return {"code": code, "meaning": self.t(de, en)}

    def tx(self, pair) -> str:
        return pair[1] if self.lang == "en" else pair[0]

    def num(self, s) -> str:
        s = str(s)
        return s.replace(".", ",") if self.lang == "de" else s.replace(",", ".")

    def el(self, sym: str) -> str:
        return self.tx(EL[sym])


def _f(v: float) -> str:
    s = f"{v:.3f}".rstrip("0").rstrip(".")
    return s


def _comp(ctx: _Ctx, d: dict) -> dict:
    out = {}
    for k, v in d.items():
        if v == "bal":
            out[k] = ctx.t("Rest", "balance")
        else:
            out[k] = ctx.num(v)
    return out


def _found(ctx, code, system, family, parts, summary, refs, comp=None, unknown=None, **kw) -> dict:
    e = {"_kind": "found", "code": code, "system": system, "family": family, "parts": parts, "summary": summary,
         "refs": list(dict.fromkeys(refs))}
    if comp:
        e["composition"] = _comp(ctx, comp)
    if unknown:
        e["_unknown"] = list(unknown)
    e.update(kw)
    return e


def _qual(code, meaning, refs=None) -> dict:
    q = {"_kind": "qual", "code": code, "meaning": meaning}
    if refs:
        q["refs"] = list(refs)
    return q


# ============================================================================ Aluminium (EN 573, EN 515, EN 1780-1)
AL_SERIES = {
    "1": ("Serie 1xxx: Reinaluminium (mindestens 99,00 % Al)", "series 1xxx: unalloyed aluminium (at least 99.00 % Al)",
          "Reinaluminium", "unalloyed aluminium"),
    "2": ("Serie 2xxx: Hauptlegierungselement Kupfer, aushärtbar", "series 2xxx: main alloying element copper, heat-treatable",
          "AlCu-Legierung", "AlCu alloy"),
    "3": ("Serie 3xxx: Hauptlegierungselement Mangan, nicht aushärtbar",
          "series 3xxx: main alloying element manganese, not heat-treatable", "AlMn-Legierung", "AlMn alloy"),
    "4": ("Serie 4xxx: Hauptlegierungselement Silicium", "series 4xxx: main alloying element silicon",
          "AlSi-Legierung", "AlSi alloy"),
    "5": ("Serie 5xxx: Hauptlegierungselement Magnesium, nicht aushärtbar",
          "series 5xxx: main alloying element magnesium, not heat-treatable", "AlMg-Legierung", "AlMg alloy"),
    "6": ("Serie 6xxx: Magnesium und Silicium (Mg₂Si), aushärtbar", "series 6xxx: magnesium and silicon (Mg₂Si), heat-treatable",
          "AlMgSi-Legierung", "AlMgSi alloy"),
    "7": ("Serie 7xxx: Hauptlegierungselement Zink (meist mit Mg, oft Cu), aushärtbar",
          "series 7xxx: main alloying element zinc (usually with Mg, often Cu), heat-treatable", "AlZn-Legierung", "AlZn alloy"),
    "8": ("Serie 8xxx: sonstige Legierungselemente (z. B. Eisen, Lithium)",
          "series 8xxx: other alloying elements (e.g. iron, lithium)", "Al-Legierung mit sonstigen Elementen",
          "alloy with other elements"),
}
# numerische Bezeichnung -> Bezeichnung mit chemischen Symbolen (EN 573-3)
AL_CHEM = {"1050A": "Al99,5", "1200": "Al99,0", "3003": "AlMn1Cu", "5005": "AlMg1(B)", "5052": "AlMg2,5",
           "5083": "AlMg4,5Mn0,7", "5086": "AlMg4", "5754": "AlMg3", "6060": "AlMgSi", "6061": "AlMg1SiCu",
           "6063": "AlMg0,7Si", "6005A": "AlSiMg(A)", "6082": "AlSi1MgMn", "2014": "AlCu4SiMg", "2017A": "AlCu4MgSi(A)",
           "2024": "AlCu4Mg1", "7020": "AlZn4,5Mg1", "7075": "AlZn5,5MgCu", "8011A": "AlFeSi(A)"}
AL_CHEM_REV = {v.replace(" ", ""): k for k, v in AL_CHEM.items()}
# Hauptlegierungselemente, Massenanteil in % (EN 573-3)
AL_COMP = {
    "1050A": {"Al": "≥ 99.50"},
    "3003": {"Mn": "1.0–1.5", "Cu": "0.05–0.20"},
    "5052": {"Mg": "2.2–2.8", "Cr": "0.15–0.35"},
    "5083": {"Mg": "4.0–4.9", "Mn": "0.40–1.0", "Cr": "0.05–0.25"},
    "5086": {"Mg": "3.5–4.5", "Mn": "0.20–0.7", "Cr": "0.05–0.25"},
    "5754": {"Mg": "2.6–3.6"},
    "6060": {"Mg": "0.35–0.6", "Si": "0.30–0.6"},
    "6061": {"Mg": "0.8–1.2", "Si": "0.40–0.8", "Cu": "0.15–0.40", "Cr": "0.04–0.35"},
    "6082": {"Si": "0.7–1.3", "Mg": "0.6–1.2", "Mn": "0.40–1.0"},
    "2017A": {"Cu": "3.5–4.5", "Mg": "0.40–1.0", "Mn": "0.40–1.0", "Si": "0.20–0.8"},
    "2024": {"Cu": "3.8–4.9", "Mg": "1.2–1.8", "Mn": "0.30–0.9"},
    "7020": {"Zn": "4.0–5.0", "Mg": "1.0–1.4"},
    "7075": {"Zn": "5.1–6.1", "Mg": "2.1–2.9", "Cu": "1.2–2.0", "Cr": "0.18–0.28"},
    "8011A": {"Fe": "0.50–1.0", "Si": "0.40–0.8"},
}

AL_H1 = {
    "1": ("kaltverfestigt (nur kaltumgeformt)", "strain-hardened only"),
    "2": ("kaltverfestigt und rückgeglüht (teilentfestigt)", "strain-hardened and partially annealed"),
    "3": ("kaltverfestigt und stabilisiert (Wärmebehandlung bei niedriger Temperatur, nur Mg-haltige Legierungen)",
          "strain-hardened and stabilized (low-temperature heat treatment, Mg-containing alloys only)"),
    "4": ("kaltverfestigt und einbrennlackiert oder beschichtet (dabei leicht entfestigt)",
          "strain-hardened and lacquered or painted (slightly softened by the curing heat)"),
}
H_DEG = {
    "1": ("zwischen O und ¼-hart", "between O and quarter hard"),
    "2": ("¼-hart (viertelhart)", "quarter hard"),
    "3": ("zwischen ¼- und ½-hart", "between quarter and half hard"),
    "4": ("½-hart (halbhart)", "half hard"),
    "5": ("zwischen ½- und ¾-hart", "between half and three-quarter hard"),
    "6": ("¾-hart (dreiviertelhart)", "three-quarter hard"),
    "7": ("zwischen ¾-hart und voll hart", "between three-quarter hard and full hard"),
    "8": ("voll hart", "full hard"),
    "9": ("extrahart (fester als voll hart)", "extra hard (beyond full hard)"),
}
AL_SPECIAL = {
    "F": ("Herstellungszustand, ohne festgelegte mechanische Grenzwerte", "as fabricated, no mechanical property limits"),
    "O": ("weichgeglüht (niedrigste Festigkeit, höchste Umformbarkeit)", "annealed (lowest strength, best formability)"),
    "O1": ("bei hoher Temperatur (etwa wie beim Lösungsglühen) geglüht und langsam abgekühlt",
           "annealed at high temperature (about solution-treatment temperature) and slowly cooled"),
    "O2": ("thermomechanisch behandelt (für hohe Umformbarkeit, z. B. superplastisches Umformen)",
           "thermomechanically processed (for high formability, e.g. superplastic forming)"),
    "O3": ("homogenisiert", "homogenized"),
    "W": ("lösungsgeglüht, instabiler Zustand (lagert bei Raumtemperatur weiter aus)",
          "solution heat-treated, unstable temper (continues to age at room temperature)"),
    "H111": ("weichgeglüht und danach geringfügig kaltverfestigt (z. B. durch Recken oder Richten), weniger als H11",
             "annealed and then slightly strain-hardened (e.g. by stretching or levelling), less than H11"),
    "H112": ("geringfügig kaltverfestigt durch Warmumformung oder begrenzte Kaltumformung, mit festgelegten Grenzwerten",
             "slightly strain-hardened from hot working or limited cold work, with specified property limits"),
    "H116": ("kaltverfestigter Sonderzustand für AlMg-Legierungen mit festgelegter Beständigkeit gegen Schicht- und "
             "interkristalline Korrosion",
             "special strain-hardened temper for AlMg alloys with specified resistance to exfoliation and intergranular "
             "corrosion"),
    "H321": ("kaltverfestigt und thermisch stabilisiert, Sonderzustand für AlMg-Legierungen mit festgelegter Beständigkeit "
             "gegen Schicht- und interkristalline Korrosion",
             "strain-hardened and thermally stabilized, special temper for AlMg alloys with specified resistance to "
             "exfoliation and intergranular corrosion"),
}
AL_T = {
    "1": ("abgekühlt aus der Warmformgebung und kaltausgelagert", "cooled from hot working and naturally aged"),
    "2": ("abgekühlt aus der Warmformgebung, kaltumgeformt und kaltausgelagert",
          "cooled from hot working, cold worked and naturally aged"),
    "3": ("lösungsgeglüht, kaltumgeformt und kaltausgelagert", "solution heat-treated, cold worked and naturally aged"),
    "4": ("lösungsgeglüht und kaltausgelagert", "solution heat-treated and naturally aged"),
    "5": ("abgekühlt aus der Warmformgebung und warmausgelagert", "cooled from hot working and artificially aged"),
    "6": ("lösungsgeglüht und warmausgelagert", "solution heat-treated and artificially aged"),
    "7": ("lösungsgeglüht und überaltert (über den Festigkeitshöchstwert hinaus warmausgelagert)",
          "solution heat-treated and overaged (aged beyond peak strength)"),
    "8": ("lösungsgeglüht, kaltumgeformt und warmausgelagert", "solution heat-treated, cold worked and artificially aged"),
    "9": ("lösungsgeglüht, warmausgelagert und kaltumgeformt", "solution heat-treated, artificially aged and cold worked"),
    "10": ("abgekühlt aus der Warmformgebung, kaltumgeformt und warmausgelagert",
           "cooled from hot working, cold worked and artificially aged"),
}
AL_T7 = {
    "3": ("überaltert für höchste Beständigkeit gegen Spannungsrisskorrosion",
          "overaged for best resistance to stress corrosion cracking"),
    "4": ("überaltert, zwischen T73 und T76", "overaged, between T73 and T76"),
    "6": ("überaltert für erhöhte Beständigkeit gegen Schichtkorrosion", "overaged for improved exfoliation corrosion resistance"),
}
T_STRESS = {
    "51": ("durch kontrolliertes Recken entspannt", "stress-relieved by controlled stretching"),
    "510": ("durch kontrolliertes Recken entspannt, danach nicht gerichtet",
            "stress-relieved by controlled stretching, no further straightening"),
    "511": ("durch kontrolliertes Recken entspannt, geringfügiges Nachrichten zulässig",
            "stress-relieved by controlled stretching, minor straightening allowed"),
    "52": ("durch kontrolliertes Stauchen entspannt", "stress-relieved by controlled compression"),
    "54": ("durch kombiniertes Recken und Stauchen entspannt", "stress-relieved by combined stretching and compression"),
}
MG_T = {
    "2": ("geglüht (nur Gussstücke)", "annealed (cast products only)"),
    "3": ("lösungsgeglüht und kaltumgeformt", "solution heat-treated and cold worked"),
    "4": ("lösungsgeglüht", "solution heat-treated"),
    "5": ("nur warmausgelagert", "artificially aged only"),
    "6": ("lösungsgeglüht und warmausgelagert", "solution heat-treated and artificially aged"),
    "7": ("lösungsgeglüht und stabilisiert", "solution heat-treated and stabilized"),
    "8": ("lösungsgeglüht, kaltumgeformt und warmausgelagert", "solution heat-treated, cold worked and artificially aged"),
    "9": ("lösungsgeglüht, warmausgelagert und kaltumgeformt", "solution heat-treated, artificially aged and cold worked"),
    "10": ("warmausgelagert und kaltumgeformt", "artificially aged and cold worked"),
}
MG_H1 = {
    "1": ("kaltverfestigt", "strain-hardened only"),
    "2": ("kaltverfestigt und teilweise rückgeglüht", "strain-hardened and partially annealed"),
    "3": ("kaltverfestigt und stabilisiert", "strain-hardened and stabilized"),
}

TEMP_AL = r"(?:F|O[1-3]?|W|H\d{2,3}|T\d{1,5})"
TEMPS_AL = rf"{TEMP_AL}(?:/{TEMP_AL})*"
TEMP_MG = r"(?:F|O|W|H\d{2}|T\d{1,2})"


def _temper(code: str, ctx: _Ctx, mg: bool = False):
    """Ein Zustandssymbol (ohne „/“) -> (parts, unknown). Aluminium nach EN 515, Magnesium nach ASTM B296."""
    t = ctx.t
    if mg:
        if code in ("F", "O", "W"):
            return [ctx.p(code, *AL_SPECIAL[code])], []
        m = re.fullmatch(r"H(\d)(\d)", code)
        if m:
            if code in ("H10", "H11"):
                return [ctx.p(code, "leicht kaltverfestigt", "slightly strain-hardened")], []
            if m[1] in MG_H1 and m[2] in H_DEG and m[2] != "1":
                return [ctx.p(code, f"{ctx.tx(MG_H1[m[1]])}, {m[2]} = {ctx.tx(H_DEG[m[2]])}",
                              f"{ctx.tx(MG_H1[m[1]])}, {m[2]} = {ctx.tx(H_DEG[m[2]])}")], []
            return [], [code]
        m = re.fullmatch(r"T(\d{1,2})", code)
        if m and m[1] in MG_T:
            return [ctx.p(code, *MG_T[m[1]])], []
        return [], [code]
    if code in AL_SPECIAL:
        return [ctx.p(code, *AL_SPECIAL[code])], []
    m = re.fullmatch(r"H(\d)(\d)(\d?)", code)
    if m:
        if m[1] in AL_H1 and m[2] in H_DEG:
            parts = [ctx.p(f"H{m[1]}{m[2]}", f"{ctx.tx(AL_H1[m[1]])}, {m[2]} = {ctx.tx(H_DEG[m[2]])}",
                           f"{ctx.tx(AL_H1[m[1]])}, {m[2]} = {ctx.tx(H_DEG[m[2]])}")]
            return parts, ([m[3] + t(f" (3. Ziffer in {code})", f" (third digit in {code})")] if m[3] else [])
        return [], [code]
    m = re.fullmatch(r"T(\d+)", code)
    if m:
        rest = m[1]
        if rest.startswith("10") and len(rest) == 2:
            return [ctx.p("T10", *AL_T["10"])], []
        main, extra = rest[0], rest[1:]
        if main not in AL_T:
            return [], [code]
        parts = []
        if main == "7" and extra[:1] in AL_T7:
            parts.append(ctx.p("T7" + extra[0], f"{ctx.tx(AL_T['7'])}; {ctx.tx(AL_T7[extra[0]])}",
                               f"{ctx.tx(AL_T['7'])}; {ctx.tx(AL_T7[extra[0]])}"))
            extra = extra[1:]
        else:
            parts.append(ctx.p("T" + main, *AL_T[main]))
        if extra:
            if extra in T_STRESS:
                parts.append(ctx.p(extra, *T_STRESS[extra]))
            else:
                return parts, [extra + t(f" (in {code})", f" (in {code})")]
        return parts, []
    return [], [code]


def _tempers(s: str, ctx: _Ctx, mg: bool = False):
    parts, unk = [], []
    codes = s.split("/")
    for c in codes:
        p, u = _temper(c, ctx, mg)
        parts += p
        unk += u
    if len(codes) > 1:
        parts.append(ctx.p("/", "Schrägstrich: das Erzeugnis erfüllt die Anforderungen beider Zustände",
                           "slash: the product meets the requirements of both tempers"))
    return parts, unk


def _temper_text(parts) -> str:
    return "; ".join(p["meaning"] for p in parts if p["code"] != "/")


def _al_core(ctx, code, num, var, temp, pre_parts, system="EN 573"):
    t = ctx.t
    unk = []
    parts = list(pre_parts)
    series = num[0]
    if series not in AL_SERIES:
        return None
    s_de, s_en, short_de, short_en = AL_SERIES[series]
    if series == "1":
        d2 = num[1]
        imp = t("keine besondere Begrenzung einzelner Verunreinigungen", "no special control of individual impurities") \
            if d2 == "0" else t("besondere Begrenzung einzelner Verunreinigungen", "special control of individual impurities")
        purity = f"99,{num[2:]}" if ctx.lang == "de" else f"99.{num[2:]}"
        parts.append(ctx.p(num, f"{s_de}; 2. Ziffer {d2}: {imp}; {num[2:]}: Mindestgehalt Aluminium {purity} %",
                           f"{s_en}; 2nd digit {d2}: {imp}; {num[2:]}: minimum aluminium content {purity} %"))
        fam = t("Reinaluminium (Knetwerkstoff)", "unalloyed wrought aluminium")
    else:
        d2 = num[1]
        mod = t("Originallegierung", "original alloy") if d2 == "0" else t(f"{d2}. Abwandlung der Originallegierung",
                                                                           f"modification {d2} of the original alloy")
        parts.append(ctx.p(num, f"{s_de}; 2. Ziffer {d2}: {mod}; {num[2:]}: Kennzahl der Legierung (ohne Zahlenbedeutung)",
                           f"{s_en}; 2nd digit {d2}: {mod}; {num[2:]}: alloy identifier (no numerical meaning)"))
        fam = t("Aluminium-Knetlegierung", "wrought aluminium alloy")
    if var:
        parts.append(ctx.p(var, "nationale Variante einer registrierten Legierung (leicht abweichende Zusammensetzungsgrenzen)",
                           "national variation of a registered alloy (slightly different composition limits)"))
    tparts = []
    if temp:
        tparts, u = _tempers(temp, ctx)
        parts += tparts
        unk += u
    key = num + (var or "")
    chem = AL_CHEM.get(key)
    refs = R_AL + (R_AL3 if (key in AL_COMP or chem) else []) + (R_T if temp else [])
    s = t(f"{code}: {fam} {key}", f"{code}: {fam} {key}")
    s += f" ({chem}, {t(short_de, short_en)})" if chem else f" ({t(short_de, short_en)})"
    if tparts:
        s += t(f", Zustand {temp}: {_temper_text(tparts)}", f", temper {temp}: {_temper_text(tparts)}")
    s += "."
    return _found(ctx, code, "EN 573 / EN 515" if temp else system, fam, parts, s, refs, AL_COMP.get(key), unk)


def _r_al_num(m, ctx):
    t = ctx.t
    pre = []
    if m["en"]:
        pre.append(ctx.p("EN", "Europäische Norm", "European Standard"))
    pre.append(ctx.p("A", "Aluminium", "aluminium"))
    pre.append(ctx.p("W", "Knetwerkstoff (wrought)", "wrought product"))
    return _al_core(ctx, m.group(0), m["num"], m["var"], m["temp"], pre)


def _r_al_bare(m, ctx):
    """1050A-O, 5052-H32: numerische Al-Bezeichnung ohne „EN AW-“, an einem EN-515-Zustand erkennbar."""
    pre = [ctx.p(m["num"] + (m["var"] or ""), "vierstellige Aluminium-Legierungsnummer ohne Vorsatz „EN AW-“",
                 "four-digit aluminium alloy number without the prefix “EN AW-”")]
    e = _al_core(ctx, m.group(0), m["num"], m["var"], m["temp"], [])
    if e:
        e["parts"] = pre + e["parts"]
    return e


def _r_al_ac(m, ctx):
    t = ctx.t
    num = m["num"]
    groups = {"2": ("AlCu", "Kupfer", "copper"), "4": ("AlSi", "Silicium", "silicon"), "5": ("AlMg", "Magnesium", "magnesium"),
              "7": ("AlZn", "Zink", "zinc")}
    if num[0] not in groups:
        return None
    g = groups[num[0]]
    parts = [ctx.p("EN", "Europäische Norm", "European Standard"), ctx.p("A", "Aluminium", "aluminium"),
             ctx.p("C", "Gusswerkstoff (casting)", "casting"),
             ctx.p(num, f"Legierungsgruppe {g[0]} (1. Ziffer {num[0]}: Hauptlegierungselement {g[1]}); "
                        f"übrige Ziffern: Kennzahl der Legierung",
                   f"alloy group {g[0]} (1st digit {num[0]}: main alloying element {g[2]}); remaining digits: alloy identifier")]
    fam = t("Aluminium-Gusslegierung", "cast aluminium alloy")
    s = t(f"{m.group(0)}: Aluminium-Gusslegierung der Gruppe {g[0]}.", f"{m.group(0)}: cast aluminium alloy of group {g[0]}.")
    return _found(ctx, m.group(0), "EN 1780-1", fam, parts, s, ["en-1780-1"])


AL_EL = "Mg|Si|Cu|Mn|Zn|Fe|Cr|Ni|Ti|Zr|Li|Pb|Bi|Be|Sn|Ag|Sc|V|B"


def _el_list(body: str, allowed=None):
    """'Mg4,5Mn0,7' -> [('Mg','4,5'), ('Mn','0,7')]; None, wenn ein Symbol unbekannt ist."""
    out = []
    pos = 0
    for mm in re.finditer(r"([A-Z][a-z]?)(\d+(?:[,.]\d+)?)?", body):
        if mm.start() != pos:
            return None
        sym = mm[1]
        if sym not in EL or (allowed and sym not in allowed):
            return None
        out.append((sym, mm[2]))
        pos = mm.end()
    if pos != len(body):
        return None
    return out


def _chem_parts(ctx, els, base_de, base_en):
    parts = []
    for sym, n in els:
        if n:
            parts.append(ctx.p(sym + n, f"{ctx.el(sym)}, Nenngehalt etwa {ctx.num(n)} % (Massenanteil)",
                               f"{ctx.el(sym)}, nominal content about {ctx.num(n)} % (by mass)"))
        else:
            parts.append(ctx.p(sym, f"{ctx.el(sym)} enthalten, Gehalt nicht im Namen angegeben (geringerer Anteil)",
                               f"{ctx.el(sym)} present, content not stated in the name (smaller amount)"))
    return parts


def _r_al_chem(m, ctx):
    t = ctx.t
    body = m["body"]
    parts = []
    if m["en"]:
        parts += [ctx.p("EN", "Europäische Norm", "European Standard"), ctx.p("A", "Aluminium", "aluminium"),
                  ctx.p("W", "Knetwerkstoff (wrought)", "wrought product")]
    parts.append(ctx.p("Al", "Grundmetall Aluminium", "base metal aluminium"))
    pm = re.match(r"99(?:[,.](\d{1,2}))?", body)
    if pm:
        purity = pm.group(0)
        parts.append(ctx.p(purity, f"Reinaluminium mit mindestens {ctx.num(purity)} % Al",
                           f"unalloyed aluminium with at least {ctx.num(purity)} % Al"))
        rest = body[pm.end():]
    else:
        rest = body
    els = _el_list(rest, AL_EL.split("|")) if rest else []
    if els is None:
        return None
    parts += _chem_parts(ctx, els, "", "")
    if m["var"]:
        parts.append(ctx.p(m["var"], "Kennbuchstabe einer nationalen Variante", "letter for a national variation"))
    unk = []
    tparts = []
    if m["temp"]:
        tparts, unk = _tempers(m["temp"], ctx)
        parts += tparts
    key = ("Al" + body + (m["var"] or "")).replace(".", ",")
    num = AL_CHEM_REV.get(key)
    refs = ["en-573-2"] + (R_AL3 if num else []) + (R_T if m["temp"] else [])
    if num:
        parts.append(ctx.p("≙ " + num, f"entspricht der numerischen Bezeichnung EN AW-{num} (EN 573-3)",
                           f"corresponds to the numerical designation EN AW-{num} (EN 573-3)"))
    fam = t("Reinaluminium (Knetwerkstoff)", "unalloyed wrought aluminium") if pm and not els \
        else t("Aluminium-Knetlegierung", "wrought aluminium alloy")
    s = t(f"{m.group(0)}: {fam}, Bezeichnung mit chemischen Symbolen", f"{m.group(0)}: {fam}, chemical-symbol designation")
    if num:
        s += f" (EN AW-{num})"
    if tparts:
        s += t(f", Zustand {m['temp']}: {_temper_text(tparts)}", f", temper {m['temp']}: {_temper_text(tparts)}")
    s += "."
    return _found(ctx, m.group(0), "EN 573-2" + (" / EN 515" if m["temp"] else ""), fam, parts, s, refs,
                  AL_COMP.get(num) if num else None, unk)


# ============================================================================ Stahl (EN 10027-1/-2)
TREAT = {
    "A": ("weichgeglüht", "soft annealed"),
    "AC": ("geglüht zur Erzielung kugeliger Carbide", "annealed to achieve spheroidized carbides"),
    "AR": ("wie gewalzt", "as rolled"),
    "AT": ("lösungsgeglüht", "solution annealed"),
    "C": ("kaltverfestigt (z. B. kaltgezogen)", "cold work hardened (e.g. cold drawn)"),
    "CR": ("kaltgewalzt", "cold rolled"),
    "FP": ("behandelt auf Ferrit-Perlit-Gefüge und Härtespanne", "treated to ferrite-pearlite structure and hardness range"),
    "H": ("mit festgelegter Härtbarkeit", "with specified hardenability"),
    "LC": ("leicht kalt nachgezogen bzw. nachgewalzt", "skin passed (lightly cold drawn or rolled)"),
    "M": ("thermomechanisch umgeformt", "thermomechanically formed"),
    "N": ("normalgeglüht oder normalisierend umgeformt", "normalized or normalized formed"),
    "NT": ("normalgeglüht und angelassen", "normalized and tempered"),
    "P": ("ausscheidungsgehärtet", "precipitation hardened"),
    "Q": ("abgeschreckt", "quenched"),
    "QA": ("luftgehärtet", "air quenched"),
    "QO": ("ölgehärtet", "oil quenched"),
    "QT": ("vergütet (gehärtet und angelassen)", "quenched and tempered"),
    "QW": ("wassergehärtet", "water quenched"),
    "S": ("behandelt auf Kaltscherbarkeit", "treated for cold shearing"),
    "SR": ("spannungsarmgeglüht", "stress relieved"),
    "T": ("angelassen", "tempered"),
    "TH": ("behandelt auf Härtespanne", "treated to hardness range"),
    "U": ("unbehandelt", "untreated"),
    "WW": ("warmverfestigt", "warm worked"),
    "Z": ("feuerverzinkt (Überzug)", "hot-dip zinc coated"),
    "ZE": ("elektrolytisch verzinkt (Überzug)", "electrolytically zinc coated"),
}
TR = r"(?P<tr>(?:\s?\+[A-Z]{1,3})*)"


def _treat(ctx, s):
    parts, unk, txt = [], [], []
    for sym in re.findall(r"\+([A-Z]{1,3})", s or ""):
        if sym in TREAT:
            parts.append(ctx.p("+" + sym, f"Behandlungszustand: {ctx.tx(TREAT[sym])}", f"treatment condition: {ctx.tx(TREAT[sym])}"))
            txt.append(ctx.tx(TREAT[sym]))
        else:
            unk.append("+" + sym)
    return parts, unk, ", ".join(txt)


STEEL_NUM = {
    "1.0038": "S235JR", "1.0044": "S275JR", "1.0577": "S355J2", "1.8901": "S460N", "1.0330": "DC01", "1.0347": "DC03",
    "1.0338": "DC04", "1.0312": "DC05", "1.0503": "C45", "1.1191": "C45E", "1.0402": "C22", "1.1151": "C22E",
    "1.7225": "42CrMo4", "1.6582": "34CrNiMo6", "1.7131": "16MnCr5", "1.3505": "100Cr6",
    "1.4301": "X5CrNi18-10", "1.4307": "X2CrNi18-9", "1.4401": "X5CrNiMo17-12-2", "1.4404": "X2CrNiMo17-12-2",
    "1.4541": "X6CrNiTi18-10", "1.4571": "X6CrNiMoTi17-12-2", "1.4016": "X6Cr17", "1.4462": "X2CrNiMoN22-5-3",
}
STEEL_NAME = {v: k for k, v in STEEL_NUM.items()}
STEEL_AISI = {"X5CrNi18-10": "304", "X2CrNi18-9": "304L", "X5CrNiMo17-12-2": "316", "X2CrNiMo17-12-2": "316L",
              "X6CrNiMoTi17-12-2": "316Ti", "X6CrNiTi18-10": "321", "X6Cr17": "430", "42CrMo4": "4140"}
STEEL_USE = {
    "C45E": ("Vergütungsstahl (EN 10083-2)", "quenching and tempering steel (EN 10083-2)", "en-10083-2"),
    "C45": ("Vergütungsstahl (EN 10083-2)", "quenching and tempering steel (EN 10083-2)", "en-10083-2"),
    "C22E": ("Vergütungsstahl (EN 10083-2)", "quenching and tempering steel (EN 10083-2)", "en-10083-2"),
    "42CrMo4": ("Vergütungsstahl (EN 10083-3)", "quenching and tempering steel (EN 10083-3)", "en-10083-3"),
    "34CrNiMo6": ("Vergütungsstahl (EN 10083-3)", "quenching and tempering steel (EN 10083-3)", "en-10083-3"),
}
STEEL_COMP = {
    "C45E": ({"C": "0.42–0.50", "Mn": "0.50–0.80", "S": "≤ 0.035"}, "en-10083-2"),
    "42CrMo4": ({"C": "0.38–0.45", "Cr": "0.90–1.20", "Mo": "0.15–0.30", "Mn": "0.60–0.90"}, "en-10083-3"),
    "X5CrNi18-10": ({"C": "≤ 0.07", "Cr": "17.5–19.5", "Ni": "8.0–10.5"}, "en-10088-1"),
    "X2CrNiMo17-12-2": ({"C": "≤ 0.030", "Cr": "16.5–18.5", "Ni": "10.0–13.0", "Mo": "2.00–2.50"}, "en-10088-1"),
    "X6CrNiMoTi17-12-2": ({"C": "≤ 0.08", "Cr": "16.5–18.5", "Ni": "10.5–13.5", "Mo": "2.00–2.50", "Ti": "5×C – 0.70"},
                          "en-10088-1"),
    "X6Cr17": ({"C": "≤ 0.08", "Cr": "16.0–18.0"}, "en-10088-1"),
}

IMPACT = {"J": "27", "K": "40", "L": "60"}
IMPACT_T = {"R": "+20", "0": "0", "1": "−10", "2": "−20", "3": "−30", "4": "−40", "5": "−50", "6": "−60"}
S_EXTRA = {
    "A": ("ausscheidungshärtend", "precipitation hardening"),
    "M": ("thermomechanisch gewalzt", "thermomechanically rolled"),
    "N": ("normalgeglüht oder normalisierend gewalzt", "normalized or normalized rolled"),
    "Q": ("vergütet", "quenched and tempered"),
    "C": ("mit besonderer Kaltumformbarkeit", "with special cold formability"),
    "D": ("für Schmelztauchüberzüge", "for hot-dip coating"),
    "E": ("zum Emaillieren", "for enamelling"),
    "F": ("zum Schmieden", "for forging"),
    "H": ("für Hohlprofile", "for hollow sections"),
    "L": ("für tiefe Temperaturen", "for low temperatures"),
    "P": ("für Spundbohlen", "for sheet piling"),
    "S": ("für den Schiffbau", "for shipbuilding"),
    "T": ("für Rohre", "for tubes"),
    "W": ("wetterfest", "weathering (atmospheric corrosion resistant)"),
}
P_EXTRA = {
    "B": ("für Gasflaschen", "for gas cylinders"),
    "H": ("für hohe Temperaturen", "for elevated temperatures"),
    "L": ("für tiefe Temperaturen", "for low temperatures"),
    "M": ("thermomechanisch gewalzt", "thermomechanically rolled"),
    "N": ("normalgeglüht oder normalisierend gewalzt", "normalized or normalized rolled"),
    "Q": ("vergütet", "quenched and tempered"),
    "R": ("für Raumtemperatur", "for room temperature"),
    "S": ("für einfache Druckbehälter", "for simple pressure vessels"),
    "T": ("für Rohre", "for tubes"),
    "X": ("für hohe und tiefe Temperaturen", "for high and low temperatures"),
}
L_EXTRA = {k: S_EXTRA[k] for k in ("M", "N", "Q")}
G1_LETTER = {
    "S": ("Stahl für den Stahlbau", "steel for structural purposes", "Mindeststreckgrenze", "minimum yield strength"),
    "P": ("Stahl für Druckbehälter", "steel for pressure purposes", "Mindeststreckgrenze", "minimum yield strength"),
    "L": ("Stahl für Leitungsrohre", "steel for line pipe", "Mindeststreckgrenze", "minimum yield strength"),
    "E": ("Maschinenbaustahl", "engineering steel", "Mindeststreckgrenze", "minimum yield strength"),
}


def _steel_suffix(ctx, s, table):
    """Zusatzsymbole hinter der Festigkeitszahl -> (parts, unknown, short texts)."""
    parts, unk, txt = [], [], []
    i = 0
    if table is S_EXTRA and len(s) >= 2 and s[0] in IMPACT and s[1] in IMPACT_T:
        e, temp = IMPACT[s[0]], IMPACT_T[s[1]]
        temp_en = temp.replace("−", "-")
        parts.append(ctx.p(s[:2], f"Kerbschlagarbeit mindestens {e} J bei {temp} °C", f"impact energy at least {e} J at {temp_en} °C"))
        txt.append(ctx.t(f"Kerbschlagarbeit ≥ {e} J bei {temp} °C", f"impact energy ≥ {e} J at {temp_en} °C"))
        i = 2
    while i < len(s):
        ch = s[i]
        if ch == "G" and table is not None:
            mm = re.match(r"G\d*", s[i:])
            g = mm.group(0)
            parts.append(ctx.p(g, "weitere Merkmale nach der Produktnorm", "other characteristics per the product standard"))
            i += len(g)
            continue
        if ch in table:
            parts.append(ctx.p(ch, *table[ch]))
            txt.append(ctx.tx(table[ch]))
            i += 1
            continue
        unk.append(s[i:])
        break
    return parts, unk, txt


def _steel_extra_info(ctx, name, parts, refs):
    """Werkstoffnummer, AISI-Entsprechung und Verwendung zu einem bekannten Kurznamen."""
    extra = []
    num = STEEL_NAME.get(name)
    if num:
        parts.append(ctx.p("≙ " + num, f"Werkstoffnummer nach EN 10027-2: {num}", f"material number per EN 10027-2: {num}"))
        refs.append("en-10027-2")
        extra.append(ctx.t(f"Werkstoffnummer {num}", f"material number {num}"))
    if name in STEEL_AISI:
        parts.append(ctx.p("≈ AISI " + STEEL_AISI[name], f"vergleichbar mit AISI {STEEL_AISI[name]} (nicht identisch)",
                           f"comparable to AISI {STEEL_AISI[name]} (not identical)"))
    if name in STEEL_USE:
        u = STEEL_USE[name]
        extra.append(ctx.t(u[0], u[1]))
        refs.append(u[2])
    return extra


def _r_steel_g1(m, ctx):
    t = ctx.t
    letter, val, suf = m["l"], m["v"], m["suf"] or ""
    d = G1_LETTER[letter]
    parts = []
    if m["g"]:
        parts.append(ctx.p("G", "Stahlguss (Vorsatz G)", "cast steel (prefix G)"))
    parts.append(ctx.p(letter, f"{d[0]} (Hauptsymbol, Gruppe 1: nach Verwendung und Eigenschaften)",
                       f"{d[1]} (main symbol, group 1: by application and properties)"))
    parts.append(ctx.p(val, f"{d[2]} {val} MPa (für die kleinste Erzeugnisdicke)", f"{d[3]} {val} MPa (for the smallest thickness)"))
    table = {"S": S_EXTRA, "P": P_EXTRA, "L": L_EXTRA, "E": {}}[letter]
    sp, unk, txt = _steel_suffix(ctx, suf, table)
    parts += sp
    tp, tu, ttxt = _treat(ctx, m["tr"])
    parts += tp
    unk += tu
    name = f"{letter}{val}{suf}"
    refs = ["en-10027-1"]
    if letter == "S" and re.fullmatch(r"(JR|J0|J2|K2)", suf or ""):
        refs.append("en-10025-2")
    extra = _steel_extra_info(ctx, name, parts, refs)
    fam = t("Stahlguss", "cast steel") if m["g"] else t(d[0], d[1])
    s = t(f"{m.group(0).strip()}: {fam}, {d[2]} {val} MPa", f"{m.group(0).strip()}: {fam}, {d[3]} {val} MPa")
    if txt:
        s += ", " + ", ".join(txt)
    if ttxt:
        s += ", " + ttxt
    if extra:
        s += " (" + "; ".join(extra) + ")"
    return _found(ctx, m.group(0).strip(), "EN 10027-1", fam, parts, s + ".", refs, None, unk)


def _r_steel_d(m, ctx):
    t = ctx.t
    kind = {"C": ("kaltgewalzt", "cold rolled"), "D": ("warmgewalzt, zum unmittelbaren Kaltumformen", "hot rolled, for direct cold forming"),
            "X": ("Walzart nicht vorgegeben", "rolling condition not specified")}[m["k"]]
    parts = [ctx.p("D", "Flacherzeugnis zum Kaltumformen", "flat product for cold forming"),
             ctx.p(m["k"], *kind)]
    refs = ["en-10027-1"]
    grade = m["n"]
    if m["k"] == "C":
        q = {"01": ("einfache Umformung (Grundgüte)", "simple forming (commercial quality)"),
             "03": ("Ziehgüte", "drawing quality"), "04": ("Tiefziehgüte", "deep-drawing quality"),
             "05": ("Sondertiefziehgüte", "special deep-drawing quality"),
             "06": ("Sondertiefziehgüte, interstitiell frei", "extra deep-drawing quality, interstitial free"),
             "07": ("Supertiefziehgüte", "super deep-drawing quality")}.get(grade)
        if q:
            parts.append(ctx.p(grade, f"Sortenkennzahl nach EN 10130: {ctx.tx(q)}; höhere Zahl = besser tiefziehbar",
                               f"grade number per EN 10130: {ctx.tx(q)}; higher number = better deep drawability"))
            refs.append("en-10130")
        else:
            parts.append(ctx.p(grade, "Sortenkennzahl der Produktnorm", "grade number of the product standard"))
    else:
        parts.append(ctx.p(grade, "Sortenkennzahl der Produktnorm", "grade number of the product standard"))
    unk = []
    suf = m["suf"] or ""
    sufs = {"D": ("für Schmelztauchüberzüge", "for hot-dip coating"), "EK": ("für konventionelles Emaillieren", "for conventional enamelling"),
            "ED": ("für Direktemaillierung", "for direct enamelling")}
    if suf:
        if suf in sufs:
            parts.append(ctx.p(suf, *sufs[suf]))
        else:
            unk.append(suf)
    tp, tu, ttxt = _treat(ctx, m["tr"])
    parts += tp
    unk += tu
    name = f"D{m['k']}{grade}{suf}"
    extra = _steel_extra_info(ctx, name, parts, refs)
    fam = t("Flacherzeugnis aus weichem Stahl zum Kaltumformen", "low-carbon steel flat product for cold forming")
    s = t(f"{m.group(0).strip()}: {fam}, {kind[0]}", f"{m.group(0).strip()}: {fam}, {kind[1]}")
    if extra:
        s += " (" + "; ".join(extra) + ")"
    return _found(ctx, m.group(0).strip(), "EN 10027-1", fam, parts, s + ".", refs, None, unk)


def _r_steel_h(m, ctx):
    t = ctx.t
    kind = {"C": ("kaltgewalzt", "cold rolled"), "D": ("warmgewalzt", "hot rolled"),
            "X": ("Walzart nicht vorgegeben", "rolling condition not specified")}[m["k"]]
    parts = [ctx.p("H", "höherfestes Flacherzeugnis zum Kaltumformen", "high-strength flat product for cold forming"),
             ctx.p(m["k"], *kind), ctx.p(m["n"], f"Mindeststreckgrenze {m['n']} MPa", f"minimum yield strength {m['n']} MPa")]
    sufs = {"LA": ("niedriglegiert bzw. mikrolegiert", "low alloy (micro-alloyed)"), "B": ("Bake-Hardening", "bake hardening"),
            "I": ("isotrop", "isotropic"), "P": ("phosphorlegiert", "phosphorus alloyed"), "Y": ("interstitiell frei (IF)", "interstitial free (IF)")}
    unk = []
    suf = m["suf"] or ""
    if suf:
        if suf in sufs:
            parts.append(ctx.p(suf, *sufs[suf]))
        else:
            unk.append(suf)
    fam = t("höherfestes Feinblech", "high-strength sheet steel")
    return _found(ctx, m.group(0), "EN 10027-1", fam, parts,
                  t(f"{m.group(0)}: {fam}, {kind[0]}, Mindeststreckgrenze {m['n']} MPa.",
                    f"{m.group(0)}: {fam}, {kind[1]}, minimum yield strength {m['n']} MPa."), ["en-10027-1"], None, unk)


def _r_steel_b(m, ctx):
    t = ctx.t
    parts = [ctx.p("B", "Betonstahl", "reinforcing steel"),
             ctx.p(m["v"], f"charakteristische Streckgrenze {m['v']} MPa", f"characteristic yield strength {m['v']} MPa")]
    if m["c"]:
        parts.append(ctx.p(m["c"], "Duktilitätsklasse (A normal, B hoch, C sehr hoch)", "ductility class (A normal, B high, C very high)"))
    fam = t("Betonstahl", "reinforcing steel")
    return _found(ctx, m.group(0), "EN 10027-1", fam, parts,
                  t(f"{m.group(0)}: Betonstahl mit charakteristischer Streckgrenze {m['v']} MPa.",
                    f"{m.group(0)}: reinforcing steel with characteristic yield strength {m['v']} MPa."), ["en-10027-1"])


def _r_steel_y(m, ctx):
    t = ctx.t
    forms = {"C": ("kaltgezogener Draht", "cold drawn wire"), "H": ("warmgewalzte Stäbe", "hot rolled bars"),
             "Q": ("vergüteter Draht", "quenched and tempered wire"), "S": ("Litze", "strand")}
    parts = [ctx.p("Y", "Spannstahl", "prestressing steel"),
             ctx.p(m["v"], f"Nennzugfestigkeit {m['v']} MPa", f"nominal tensile strength {m['v']} MPa"),
             ctx.p(m["c"], *forms[m["c"]])]
    fam = t("Spannstahl", "prestressing steel")
    return _found(ctx, m.group(0), "EN 10027-1", fam, parts,
                  t(f"{m.group(0)}: Spannstahl, Nennzugfestigkeit {m['v']} MPa, {forms[m['c']][0]}.",
                    f"{m.group(0)}: prestressing steel, nominal tensile strength {m['v']} MPa, {forms[m['c']][1]}."),
                  ["en-10027-1"])


def _r_steel_r(m, ctx):
    t = ctx.t
    if not m["s"] and ctx.hint != "steel":
        return {"_kind": "unknown", "text": m.group(0),
                "note": t(f"„{m.group(0)}“ ist ohne Zusammenhang mehrdeutig: Schienenstahl (EN 10027-1) oder Kupfer-Zustand "
                          f"Rm ≥ {m['v']} MPa (EN 1173).",
                          f"“{m.group(0)}” is ambiguous on its own: rail steel (EN 10027-1) or copper condition "
                          f"Rm ≥ {m['v']} MPa (EN 1173).")}
    sufs = {"Cr": ("chromlegiert", "chromium alloyed"), "Mn": ("manganlegiert", "manganese alloyed"),
            "HT": ("wärmebehandelt", "heat treated"), "LHT": ("niedriglegiert und wärmebehandelt", "low alloy, heat treated")}
    parts = [ctx.p("R", "Schienenstahl", "rail steel"), ctx.p(m["v"], f"Mindesthärte {m['v']} HBW", f"minimum hardness {m['v']} HBW")]
    if m["s"]:
        parts.append(ctx.p(m["s"], *sufs[m["s"]]))
    fam = t("Schienenstahl", "rail steel")
    return _found(ctx, m.group(0), "EN 10027-1", fam, parts,
                  t(f"{m.group(0)}: Schienenstahl mit Mindesthärte {m['v']} HBW.", f"{m.group(0)}: rail steel with minimum hardness {m['v']} HBW."),
                  ["en-10027-1"])


def _r_steel_m(m, ctx):
    t = ctx.t
    types = {"A": ("nicht kornorientiert, schlussgeglüht", "non-oriented, fully processed"),
             "N": ("kornorientiert, normale Ummagnetisierungsverluste", "grain-oriented, normal core loss"),
             "S": ("kornorientiert, verringerte Verluste", "grain-oriented, reduced core loss"),
             "P": ("kornorientiert, hohe Permeabilität", "grain-oriented, high permeability")}
    if m["k"] not in types:
        return None
    loss = int(m["v"]) / 100
    thick = int(m["d"]) / 100
    parts = [ctx.p("M", "Elektroblech", "electrical steel"),
             ctx.p(m["v"], f"höchstzulässiger Ummagnetisierungsverlust {ctx.num(_f(loss))} W/kg (100-fach angegeben)",
                   f"maximum core loss {_f(loss)} W/kg (given ×100)"),
             ctx.p(m["d"], f"Nenndicke {ctx.num(_f(thick))} mm (100-fach angegeben)", f"nominal thickness {_f(thick)} mm (given ×100)"),
             ctx.p(m["k"], *types[m["k"]])]
    fam = t("Elektroblech", "electrical steel")
    return _found(ctx, m.group(0), "EN 10027-1", fam, parts,
                  t(f"{m.group(0)}: Elektroblech, Verlust ≤ {ctx.num(_f(loss))} W/kg, Dicke {ctx.num(_f(thick))} mm.",
                    f"{m.group(0)}: electrical steel, core loss ≤ {_f(loss)} W/kg, thickness {_f(thick)} mm."), ["en-10027-1"])


UNALLOYED_SUF = {
    "C": ("besondere Kaltumformbarkeit", "special cold formability"),
    "D": ("zum Drahtziehen", "for wire drawing"),
    "E": ("vorgeschriebener Höchstgehalt an Schwefel", "prescribed maximum sulphur content"),
    "R": ("vorgeschriebener Bereich des Schwefelgehalts", "prescribed range of sulphur content"),
    "S": ("für Federn", "for springs"),
    "U": ("für Werkzeuge", "for tools"),
    "W": ("für Schweißdraht", "for welding wire"),
    "G": ("andere Merkmale", "other characteristics"),
}


def _r_steel_c(m, ctx):
    t = ctx.t
    c = int(m["c"]) / 100
    parts = []
    if m["g"]:
        parts.append(ctx.p("G", "Stahlguss (Vorsatz G)", "cast steel (prefix G)"))
    parts += [ctx.p("C", "unlegierter Stahl (Mn < 1 %), Bezeichnung nach chemischer Zusammensetzung",
                    "non-alloy steel (Mn < 1 %), designation by chemical composition"),
              ctx.p(m["c"], f"Kohlenstoff im Mittel {ctx.num(_f(c))} % (Kennzahl ÷ 100)", f"mean carbon content {_f(c)} % (number ÷ 100)")]
    unk = []
    txt = []
    for ch in m["suf"] or "":
        if ch in UNALLOYED_SUF:
            parts.append(ctx.p(ch, *UNALLOYED_SUF[ch]))
            txt.append(ctx.tx(UNALLOYED_SUF[ch]))
        else:
            unk.append(ch)
    tp, tu, ttxt = _treat(ctx, m["tr"])
    parts += tp
    unk += tu
    name = f"C{m['c']}{m['suf'] or ''}"
    refs = ["en-10027-1"]
    extra = _steel_extra_info(ctx, name, parts, refs)
    comp = None
    if name in STEEL_COMP:
        comp, r = STEEL_COMP[name]
        refs.append(r)
    fam = t("unlegierter Stahl", "non-alloy steel") if not m["g"] else t("unlegierter Stahlguss", "non-alloy cast steel")
    s = t(f"{m.group(0).strip()}: {fam} mit {ctx.num(_f(c))} % C", f"{m.group(0).strip()}: {fam} with {_f(c)} % C")
    if txt:
        s += ", " + ", ".join(txt)
    if ttxt:
        s += t(", Zustand: ", ", condition: ") + ttxt
    if extra:
        s += " (" + "; ".join(extra) + ")"
    return _found(ctx, m.group(0).strip(), "EN 10027-1", fam, parts, s + ".", refs, comp, unk)


FACTOR = {**{e: 4 for e in ("Cr", "Co", "Mn", "Ni", "Si", "W")},
          **{e: 10 for e in ("Al", "Be", "Cu", "Mo", "Nb", "Pb", "Ta", "Ti", "V", "Zr")},
          **{e: 100 for e in ("Ce", "N", "P", "S")}, "B": 1000}


def _r_steel_low(m, ctx):
    t = ctx.t
    els = re.findall(r"[A-Z][a-z]?", m["el"])
    if "".join(els) != m["el"] or any(e not in FACTOR for e in els):
        return None
    nums = m["n"].split("-")
    if len(nums) > len(els):
        return None
    c = int(m["c"]) / 100
    parts = []
    if m["g"]:
        parts.append(ctx.p("G", "Stahlguss (Vorsatz G)", "cast steel (prefix G)"))
    parts.append(ctx.p(m["c"], f"Kohlenstoff im Mittel {ctx.num(_f(c))} % (Kennzahl ÷ 100)", f"mean carbon content {_f(c)} % (number ÷ 100)"))
    parts.append(ctx.p(m["el"], "Legierungselemente " + ", ".join(ctx.el(e) for e in els) + " (nach fallendem Gehalt)",
                       "alloying elements " + ", ".join(ctx.el(e) for e in els) + " (in decreasing order of content)"))
    txt = []
    for e, n in zip(els, nums):
        f = FACTOR[e]
        v = int(n) / f
        parts.append(ctx.p(n, f"{ctx.el(e)}: {n} ÷ {f} ≈ {ctx.num(_f(v))} % (Nenngehalt)", f"{ctx.el(e)}: {n} ÷ {f} ≈ {_f(v)} % (nominal)"))
        txt.append(f"≈ {ctx.num(_f(v))} % {e}")
    rest = els[len(nums):]
    if rest:
        parts.append(ctx.p("".join(rest), ", ".join(ctx.el(e) for e in rest) + " zulegiert, Gehalt nicht im Namen angegeben",
                           ", ".join(ctx.el(e) for e in rest) + " added, content not stated in the name"))
        txt.append(t("mit ", "with ") + ", ".join(rest))
    parts.append(ctx.p(t("Faktoren", "factors"), "Teiler für die Gehaltszahlen: 4 für Cr, Co, Mn, Ni, Si, W; 10 für Al, Be, Cu, Mo, "
                                                 "Nb, Pb, Ta, Ti, V, Zr; 100 für Ce, N, P, S; 1000 für B",
                       "divisors of the content numbers: 4 for Cr, Co, Mn, Ni, Si, W; 10 for Al, Be, Cu, Mo, Nb, Pb, Ta, Ti, V, "
                       "Zr; 100 for Ce, N, P, S; 1000 for B"))
    tp, tu, ttxt = _treat(ctx, m["tr"])
    parts += tp
    name = f"{m['c']}{m['el']}{m['n']}"
    refs = ["en-10027-1"]
    extra = _steel_extra_info(ctx, name, parts, refs)
    comp = None
    if name in STEEL_COMP:
        comp, r = STEEL_COMP[name]
        refs.append(r)
    fam = t("niedriglegierter Stahl", "low-alloy steel") if not m["g"] else t("niedriglegierter Stahlguss", "low-alloy cast steel")
    s = t(f"{m.group(0).strip()}: {fam} mit {ctx.num(_f(c))} % C, ", f"{m.group(0).strip()}: {fam} with {_f(c)} % C, ") + ", ".join(txt)
    if ttxt:
        s += t(", Zustand: ", ", condition: ") + ttxt
    if extra:
        s += " (" + "; ".join(extra) + ")"
    return _found(ctx, m.group(0).strip(), "EN 10027-1", fam, parts, s + ".", refs, comp, tu)


def _r_steel_x(m, ctx):
    t = ctx.t
    els = re.findall(r"[A-Z][a-z]?", m["el"])
    if "".join(els) != m["el"] or any(e not in EL for e in els):
        return None
    nums = m["n"].split("-")
    if len(nums) > len(els):
        return None
    c = int(m["c"]) / 100
    parts = []
    if m["g"]:
        parts.append(ctx.p("G", "Stahlguss (Vorsatz G)", "cast steel (prefix G)"))
    parts += [ctx.p("X", "hochlegierter Stahl (mindestens ein Legierungselement ≥ 5 %)",
                    "high-alloy steel (at least one alloying element ≥ 5 %)"),
              ctx.p(m["c"], f"Kohlenstoff im Mittel {ctx.num(_f(c))} % (Kennzahl ÷ 100)", f"mean carbon content {_f(c)} % (number ÷ 100)"),
              ctx.p(m["el"], "Legierungselemente " + ", ".join(ctx.el(e) for e in els) + " (nach fallendem Gehalt)",
                    "alloying elements " + ", ".join(ctx.el(e) for e in els) + " (in decreasing order of content)")]
    txt = []
    cr = 0.0
    for e, n in zip(els, nums):
        parts.append(ctx.p(n, f"{ctx.el(e)} etwa {ctx.num(n)} % (Nenngehalt in %)", f"{ctx.el(e)} about {ctx.num(n)} % (nominal, in %)"))
        txt.append(f"{ctx.num(n)} % {e}")
        if e == "Cr":
            cr = float(n.replace(",", "."))
    rest = els[len(nums):]
    if rest:
        parts.append(ctx.p("".join(rest), ", ".join(ctx.el(e) for e in rest) + " zulegiert, Gehalt nicht im Namen angegeben",
                           ", ".join(ctx.el(e) for e in rest) + " added, content not stated in the name"))
        txt.append(t("mit ", "with ") + ", ".join(rest))
    tp, tu, ttxt = _treat(ctx, m["tr"])
    parts += tp
    name = f"X{m['c']}{m['el']}{m['n']}"
    refs = ["en-10027-1"]
    extra = _steel_extra_info(ctx, name, parts, refs)
    comp = None
    if name in STEEL_COMP:
        comp, r = STEEL_COMP[name]
        refs.append(r)
    stainless = cr >= 10.5 and c <= 1.2
    if stainless:
        fam = t("nichtrostender Stahl (hochlegiert)", "stainless steel (high alloy)")
    else:
        fam = t("hochlegierter Stahl", "high-alloy steel")
    if m["g"]:
        fam = t("hochlegierter Stahlguss", "high-alloy cast steel")
    s = t(f"{m.group(0).strip()}: {fam} mit {ctx.num(_f(c))} % C, ", f"{m.group(0).strip()}: {fam} with {_f(c)} % C, ") + ", ".join(txt)
    if stainless:
        s += t(" (≥ 10,5 % Cr: nichtrostend nach EN 10088-1)", " (≥ 10.5 % Cr: stainless per EN 10088-1)")
        refs.append("en-10088-1")
    if ttxt:
        s += t(", Zustand: ", ", condition: ") + ttxt
    if extra:
        s += " (" + "; ".join(extra) + ")"
    return _found(ctx, m.group(0).strip(), "EN 10027-1", fam, parts, s + ".", refs, comp, tu)


def _r_steel_hs(m, ctx):
    t = ctx.t
    nums = m["n"].split("-")
    order = ["W", "Mo", "V", "Co"]
    parts = [ctx.p("HS", "Schnellarbeitsstahl", "high-speed steel")]
    txt = []
    for e, n in zip(order, nums):
        parts.append(ctx.p(n, f"{ctx.el(e)} etwa {ctx.num(n)} %", f"{ctx.el(e)} about {ctx.num(n)} %"))
        txt.append(f"{ctx.num(n)} % {e}")
    parts.append(ctx.p(t("Reihenfolge", "order"), "Gehalte in % in der festen Reihenfolge W-Mo-V-Co",
                       "contents in % in the fixed order W-Mo-V-Co"))
    fam = t("Schnellarbeitsstahl", "high-speed steel")
    return _found(ctx, m.group(0).strip(), "EN 10027-1", fam, parts,
                  t(f"{m.group(0).strip()}: Schnellarbeitsstahl mit ", f"{m.group(0).strip()}: high-speed steel with ") + ", ".join(txt) + ".",
                  ["en-10027-1"])


STEEL_GROUPS = {
    "00": ("Grundstähle", "base steels"),
    "01": ("unlegierte Qualitätsstähle: allgemeine Baustähle mit Rm < 500 MPa",
           "non-alloy quality steels: general structural steels with Rm < 500 MPa"),
    "02": ("unlegierte Qualitätsstähle: sonstige, nicht für eine Wärmebehandlung bestimmte Baustähle mit Rm < 500 MPa",
           "non-alloy quality steels: other structural steels not intended for heat treatment, Rm < 500 MPa"),
    "03": ("unlegierte Qualitätsstähle mit im Mittel < 0,12 % C oder Rm < 400 MPa",
           "non-alloy quality steels with mean C < 0.12 % or Rm < 400 MPa"),
    "04": ("unlegierte Qualitätsstähle mit im Mittel 0,12 bis < 0,25 % C oder Rm 400 bis < 500 MPa",
           "non-alloy quality steels with mean C 0.12 to < 0.25 % or Rm 400 to < 500 MPa"),
    "05": ("unlegierte Qualitätsstähle mit im Mittel 0,25 bis < 0,55 % C oder Rm 500 bis < 700 MPa",
           "non-alloy quality steels with mean C 0.25 to < 0.55 % or Rm 500 to < 700 MPa"),
    "06": ("unlegierte Qualitätsstähle mit im Mittel ≥ 0,55 % C oder Rm ≥ 700 MPa",
           "non-alloy quality steels with mean C ≥ 0.55 % or Rm ≥ 700 MPa"),
    "07": ("unlegierte Qualitätsstähle mit höherem Phosphor- oder Schwefelgehalt",
           "non-alloy quality steels with higher phosphorus or sulphur content"),
    "08": ("legierte Qualitätsstähle", "alloy quality steels"), "09": ("legierte Qualitätsstähle", "alloy quality steels"),
    "10": ("unlegierte Edelstähle mit besonderen physikalischen Eigenschaften",
           "non-alloy special steels with special physical properties"),
    "11": ("unlegierte Edelstähle: Bau-, Maschinenbau- und Behälterstähle mit < 0,50 % C",
           "non-alloy special steels: structural, engineering and pressure vessel steels with < 0.50 % C"),
    "12": ("unlegierte Edelstähle: Maschinenbaustähle mit ≥ 0,50 % C", "non-alloy special steels: engineering steels with ≥ 0.50 % C"),
    "13": ("unlegierte Edelstähle: Bau-, Maschinenbau- und Behälterstähle mit besonderen Anforderungen",
           "non-alloy special steels: structural, engineering and pressure vessel steels with special requirements"),
    **{g: ("unlegierte Werkzeugstähle", "non-alloy tool steels") for g in ("15", "16", "17", "18")},
    **{str(g): ("legierte Werkzeugstähle", "alloy tool steels") for g in range(20, 29)},
    "32": ("Schnellarbeitsstähle mit Cobalt", "high-speed steels with cobalt"),
    "33": ("Schnellarbeitsstähle ohne Cobalt", "high-speed steels without cobalt"),
    "35": ("Wälzlagerstähle", "rolling bearing steels"),
    "36": ("Werkstoffe mit besonderen magnetischen Eigenschaften, ohne Cobalt", "materials with special magnetic properties, without cobalt"),
    "37": ("Werkstoffe mit besonderen magnetischen Eigenschaften, mit Cobalt", "materials with special magnetic properties, with cobalt"),
    "38": ("Werkstoffe mit besonderen physikalischen Eigenschaften, ohne Nickel", "materials with special physical properties, without nickel"),
    "39": ("Werkstoffe mit besonderen physikalischen Eigenschaften, mit Nickel", "materials with special physical properties, with nickel"),
    "40": ("nichtrostende Stähle mit < 2,5 % Ni, ohne Mo, Nb und Ti", "stainless steels with < 2.5 % Ni, without Mo, Nb and Ti"),
    "41": ("nichtrostende Stähle mit < 2,5 % Ni, mit Mo, ohne Nb und Ti", "stainless steels with < 2.5 % Ni, with Mo, without Nb and Ti"),
    "43": ("nichtrostende Stähle mit ≥ 2,5 % Ni, ohne Mo, Nb und Ti", "stainless steels with ≥ 2.5 % Ni, without Mo, Nb and Ti"),
    "44": ("nichtrostende Stähle mit ≥ 2,5 % Ni, mit Mo, ohne Nb und Ti", "stainless steels with ≥ 2.5 % Ni, with Mo, without Nb and Ti"),
    "45": ("nichtrostende Stähle mit Sonderzusätzen (z. B. Ti, Nb, Cu)", "stainless steels with special additions (e.g. Ti, Nb, Cu)"),
    "46": ("chemisch beständige und hochwarmfeste Nickellegierungen", "chemically resistant and high-temperature nickel alloys"),
    "47": ("hitzebeständige Stähle mit < 2,5 % Ni", "heat-resisting steels with < 2.5 % Ni"),
    "48": ("hitzebeständige Stähle mit ≥ 2,5 % Ni", "heat-resisting steels with ≥ 2.5 % Ni"),
    "49": ("hochwarmfeste Werkstoffe", "high-temperature materials"),
    "70": ("legierte Edelstähle: Cr- und Cr-B-Stähle", "alloy special steels: Cr and Cr-B steels"),
    "72": ("legierte Edelstähle: Cr-Mo-Stähle mit < 0,35 % Mo", "alloy special steels: Cr-Mo steels with < 0.35 % Mo"),
    "73": ("legierte Edelstähle: Cr-Mo-Stähle mit ≥ 0,35 % Mo", "alloy special steels: Cr-Mo steels with ≥ 0.35 % Mo"),
    "88": ("legierte Edelstähle: hochfeste schweißgeeignete Stähle", "alloy special steels: high-strength weldable steels"),
    "89": ("legierte Edelstähle: hochfeste schweißgeeignete Stähle", "alloy special steels: high-strength weldable steels"),
}
for _g in range(91, 98):
    STEEL_GROUPS[str(_g)] = STEEL_GROUPS["0" + str(_g - 90)]
STEEL_GROUPS["90"] = STEEL_GROUPS["00"]
STEEL_GROUPS["98"] = STEEL_GROUPS["99"] = STEEL_GROUPS["08"]


def _r_steel_num(m, ctx):
    t = ctx.t
    g, y = m["g"], m["y"]
    num = f"1.{g}{y}"
    parts = [ctx.p("1", "Werkstoffhauptgruppe 1: Stahl", "material main group 1: steel")]
    unk = []
    if g in STEEL_GROUPS:
        gtxt = ctx.tx(STEEL_GROUPS[g])
    elif 50 <= int(g) <= 89:
        gtxt = t("legierte Edelstähle: Bau-, Maschinenbau- und Behälterstähle (Untergruppe nach Legierungselementen)",
                 "alloy special steels: structural, engineering and pressure vessel steels (sub-group by alloying elements)")
    else:
        gtxt = None
        unk.append(t(f"Stahlgruppe {g} (in {num})", f"steel group {g} (in {num})"))
    if gtxt:
        parts.append(ctx.p(g, f"Stahlgruppennummer {g}: {gtxt}", f"steel group number {g}: {gtxt}"))
    parts.append(ctx.p(y, "Zählnummer innerhalb der Stahlgruppe", "sequential number within the steel group"))
    if m["z"]:
        parts.append(ctx.p(m["z"], "zusätzliche Zählstellen (für spätere Erweiterung vorgesehen)",
                           "additional sequential digits (reserved for future use)"))
    tp, tu, ttxt = _treat(ctx, m["tr"])
    parts += tp
    unk += tu
    refs = ["en-10027-2"]
    name = STEEL_NUM.get(num)
    comp = None
    if name:
        parts.append(ctx.p("≙ " + name, f"Kurzname nach EN 10027-1: {name}", f"steel name per EN 10027-1: {name}"))
        refs.append("en-10027-1")
        if name in STEEL_COMP:
            comp, r = STEEL_COMP[name]
            refs.append(r)
        if name in STEEL_AISI:
            parts.append(ctx.p("≈ AISI " + STEEL_AISI[name], f"vergleichbar mit AISI {STEEL_AISI[name]} (nicht identisch)",
                               f"comparable to AISI {STEEL_AISI[name]} (not identical)"))
    fam = t("Stahl", "steel")
    if g in ("40", "41", "43", "44", "45"):
        fam = t("nichtrostender Stahl", "stainless steel")
    s = t(f"{m.group(0).strip()}: Werkstoffnummer eines Stahls", f"{m.group(0).strip()}: material number of a steel")
    if gtxt:
        s += f" ({gtxt})"
    if name:
        s += t(f", Kurzname {name}", f", steel name {name}")
    if ttxt:
        s += t(", Zustand: ", ", condition: ") + ttxt
    return _found(ctx, m.group(0).strip(), "EN 10027-2", fam, parts, s + ".", refs, comp, unk)


# ---------------------------------------------------------------------------- alte DIN-Bezeichnungen
def _r_old_st(m, ctx):
    t = ctx.t
    n = int(m["n"])
    if 12 <= n <= 15 and not m["q"]:
        new = {12: "DC01", 13: "DC03", 14: "DC04", 15: "DC05"}[n]
        parts = [ctx.p("St", "Stahl (alte DIN-Bezeichnung)", "steel (former DIN designation)"),
                 ctx.p(m["n"], f"Kennzahl der Umformgüte von kaltgewalztem Feinblech (DIN 1623-1); heute {new}",
                       f"forming-quality number of cold rolled sheet (DIN 1623-1); today {new}")]
        return _found(ctx, m.group(0), "DIN 1623-1 (zurückgezogen)" if ctx.lang == "de" else "DIN 1623-1 (withdrawn)",
                      t("Feinblech zum Kaltumformen", "sheet steel for cold forming"), parts,
                      t(f"{m.group(0)}: alte DIN-Bezeichnung für kaltgewalztes Feinblech, heute {new}.",
                        f"{m.group(0)}: former DIN designation of cold rolled sheet, today {new}."), ["din-1623-1", "en-10130"])
    if n < 30:
        return None
    mpa = round(n * 9.80665)
    new = {"37-2": "S235JR", "44-2": "S275JR", "52-3": "S355J2"}.get(f"{n}-{m['q']}")
    parts = [ctx.p("St", "Stahl (alte DIN-Bezeichnung)", "steel (former DIN designation)"),
             ctx.p(m["n"], f"Mindestzugfestigkeit {n} kp/mm² (≈ {mpa} MPa)", f"minimum tensile strength {n} kp/mm² (≈ {mpa} MPa)")]
    if m["q"]:
        parts.append(ctx.p(m["q"], f"Gütegruppe {m['q']} (höhere Zahl = höhere Anforderungen an die Sprödbruchsicherheit)",
                           f"quality group {m['q']} (higher number = higher requirements on brittle-fracture safety)"))
    if new:
        parts.append(ctx.p("≙ " + new, f"heutige Bezeichnung nach EN 10025-2: {new}", f"current designation per EN 10025-2: {new}"))
    s = t(f"{m.group(0)}: alte Bezeichnung (DIN 17100) für einen allgemeinen Baustahl mit Rm ≥ {n} kp/mm²",
          f"{m.group(0)}: former designation (DIN 17100) of a general structural steel with Rm ≥ {n} kp/mm²")
    s += (t(f", heute {new}", f", today {new}") if new else "") + "."
    return _found(ctx, m.group(0), "DIN 17100 (zurückgezogen)" if ctx.lang == "de" else "DIN 17100 (withdrawn)",
                  t("Baustahl", "structural steel"), parts, s, ["din-17100"] + (["en-10025-2"] if new else []))


def _r_old_ck(m, ctx):
    t = ctx.t
    c = int(m["c"]) / 100
    new = f"C{m['c']}E"
    parts = [ctx.p("C", "unlegierter Kohlenstoffstahl", "non-alloy carbon steel"),
             ctx.p("k", "kleiner Phosphor- und Schwefelgehalt (Edelstahl)", "low phosphorus and sulphur content (special steel)"),
             ctx.p(m["c"], f"Kohlenstoff im Mittel {ctx.num(_f(c))} %", f"mean carbon content {_f(c)} %"),
             ctx.p("≙ " + new, f"heutige Bezeichnung: {new}", f"current designation: {new}")]
    tp, tu, ttxt = _treat(ctx, m["tr"])
    parts += tp
    s = t(f"{m.group(0).strip()}: alte Bezeichnung (DIN 17200) eines unlegierten Vergütungsstahls mit {ctx.num(_f(c))} % C, heute {new}",
          f"{m.group(0).strip()}: former designation (DIN 17200) of a non-alloy quenching and tempering steel with {_f(c)} % C, today {new}")
    if ttxt:
        s += t(", Zustand: ", ", condition: ") + ttxt
    return _found(ctx, m.group(0).strip(), "DIN 17200 (zurückgezogen)" if ctx.lang == "de" else "DIN 17200 (withdrawn)",
                  t("unlegierter Vergütungsstahl", "non-alloy quenching and tempering steel"), parts, s + ".",
                  ["din-17200", "en-10027-1"] + (["en-10027-1"] if tp else []), None, tu)


def _r_old_gg(m, ctx):
    t = ctx.t
    n = m["n"]
    if m["k"] == "GGG":
        new = {"40": "EN-GJS-400-15", "50": "EN-GJS-500-7", "60": "EN-GJS-600-3", "70": "EN-GJS-700-2"}.get(n)
        parts = [ctx.p("GGG", "Gusseisen mit Kugelgraphit (Sphäroguss), alte DIN-Bezeichnung",
                       "spheroidal graphite cast iron (ductile iron), former DIN designation"),
                 ctx.p(n, f"Mindestzugfestigkeit {n} kp/mm² (≈ {int(n) * 10} MPa)", f"minimum tensile strength {n} kp/mm² (≈ {int(n) * 10} MPa)")]
        std, ref, fam = "DIN 1693-1", "din-1693-1", t("Gusseisen mit Kugelgraphit", "spheroidal graphite cast iron")
    else:
        new = {"15": "EN-GJL-150", "20": "EN-GJL-200", "25": "EN-GJL-250", "30": "EN-GJL-300", "35": "EN-GJL-350"}.get(n)
        parts = [ctx.p("GG", "Gusseisen mit Lamellengraphit (Grauguss), alte DIN-Bezeichnung",
                       "lamellar graphite cast iron (grey iron), former DIN designation"),
                 ctx.p(n, f"Mindestzugfestigkeit {n} kp/mm² (≈ {int(n) * 10} MPa)", f"minimum tensile strength {n} kp/mm² (≈ {int(n) * 10} MPa)")]
        std, ref, fam = "DIN 1691", "din-1691", t("Gusseisen mit Lamellengraphit", "grey cast iron")
    if new:
        parts.append(ctx.p("≙ " + new, f"heutige Bezeichnung nach EN 1560: {new}", f"current designation per EN 1560: {new}"))
    s = t(f"{m.group(0)}: alte Bezeichnung ({std}) für {fam}, Rm ≥ {int(n) * 10} MPa", f"{m.group(0)}: former designation ({std}) of {fam}, Rm ≥ {int(n) * 10} MPa")
    s += (t(f", heute {new}", f", today {new}") if new else "") + "."
    return _found(ctx, m.group(0), std + t(" (zurückgezogen)", " (withdrawn)"), fam, parts, s, [ref] + (["en-1560"] if new else []))


# ---------------------------------------------------------------------------- SAE/AISI
SAE_CLASS = {
    "10": ("unlegierter Kohlenstoffstahl (Mn ≤ 1,00 %)", "plain carbon steel (Mn ≤ 1.00 %)"),
    "11": ("rückgeschwefelter Kohlenstoffstahl (Automatenstahl)", "resulphurized carbon steel (free machining)"),
    "12": ("rückgeschwefelter und rückphosphorter Kohlenstoffstahl", "resulphurized and rephosphorized carbon steel"),
    "13": ("Manganstahl (Mn etwa 1,75 %)", "manganese steel (Mn about 1.75 %)"),
    "15": ("unlegierter Kohlenstoffstahl mit Mn über 1,00 %", "plain carbon steel with Mn above 1.00 %"),
    "40": ("Molybdänstahl", "molybdenum steel"),
    "41": ("Chrom-Molybdän-Stahl (Cr etwa 0,5–0,95 %, Mo etwa 0,12–0,30 %)", "chromium-molybdenum steel (Cr about 0.5–0.95 %, Mo about 0.12–0.30 %)"),
    "43": ("Nickel-Chrom-Molybdän-Stahl (Ni etwa 1,8 %, Cr etwa 0,5–0,8 %, Mo etwa 0,25 %)",
           "nickel-chromium-molybdenum steel (Ni about 1.8 %, Cr about 0.5–0.8 %, Mo about 0.25 %)"),
    "46": ("Nickel-Molybdän-Stahl", "nickel-molybdenum steel"),
    "47": ("Nickel-Chrom-Molybdän-Stahl", "nickel-chromium-molybdenum steel"),
    "48": ("Nickel-Molybdän-Stahl", "nickel-molybdenum steel"),
    "51": ("Chromstahl", "chromium steel"),
    "61": ("Chrom-Vanadium-Stahl", "chromium-vanadium steel"),
    "86": ("Nickel-Chrom-Molybdän-Stahl", "nickel-chromium-molybdenum steel"),
    "87": ("Nickel-Chrom-Molybdän-Stahl", "nickel-chromium-molybdenum steel"),
    "92": ("Silicium-Mangan-Stahl", "silicon-manganese steel"),
}
SAE_COMP = {
    "1020": {"C": "0.18–0.23", "Mn": "0.30–0.60"},
    "1040": {"C": "0.37–0.44", "Mn": "0.60–0.90"},
    "4140": {"C": "0.38–0.43", "Mn": "0.75–1.00", "Cr": "0.80–1.10", "Mo": "0.15–0.25"},
    "4340": {"C": "0.38–0.43", "Mn": "0.60–0.80", "Ni": "1.65–2.00", "Cr": "0.70–0.90", "Mo": "0.20–0.30"},
}
SAE_EN = {"1020": "C22", "1040": "C40", "4140": "42CrMo4", "4340": "34CrNiMo6 / 36CrNiMo4"}


def _sae_core(ctx, code, num, h, tr, prefix):
    t = ctx.t
    cls = num[:2]
    if len(num) == 5:
        if num != "52100":
            return None
        cls_txt = ("Chrom-Wälzlagerstahl", "chromium bearing steel")
        c = int(num[2:]) / 100
    else:
        if cls not in SAE_CLASS:
            return None
        cls_txt = SAE_CLASS[cls]
        c = int(num[2:]) / 100
    parts = list(prefix)
    parts.append(ctx.p(num[:2], f"Stahlklasse {num[:2]}xx: {ctx.tx(cls_txt)}", f"steel class {num[:2]}xx: {ctx.tx(cls_txt)}"))
    parts.append(ctx.p(num[2:], f"Kohlenstoff etwa {ctx.num(_f(c))} % (in Hundertstel Prozent)", f"carbon about {_f(c)} % (in hundredths of a percent)"))
    if h:
        parts.append(ctx.p("H", "mit gewährleisteter Härtbarkeit (H-Stahl)", "with guaranteed hardenability (H steel)"))
    tp, tu, ttxt = _treat(ctx, tr)
    if tp:
        parts += [dict(p, meaning=p["meaning"] + t(" (Symbol nach EN 10027-1)", " (symbol per EN 10027-1)")) for p in tp]
    refs = ["sae-j403" if cls in ("10", "11", "12", "15") else "sae-j404"] + (["en-10027-1"] if tp else [])
    if num in SAE_EN:
        parts.append(ctx.p("≈ " + SAE_EN[num], f"vergleichbare europäische Sorte: {SAE_EN[num]} (nicht identisch)",
                           f"comparable European grade: {SAE_EN[num]} (not identical)"))
    fam = t("unlegierter Stahl", "carbon steel") if cls in ("10", "11", "12", "15") else t("niedriglegierter Stahl", "low-alloy steel")
    s = t(f"{code}: {ctx.tx(cls_txt)} mit etwa {ctx.num(_f(c))} % C", f"{code}: {ctx.tx(cls_txt)} with about {_f(c)} % C")
    if ttxt:
        s += t(", Zustand: ", ", condition: ") + ttxt
    return _found(ctx, code, "SAE J403/J404 (AISI)", fam, parts, s + ".", refs, SAE_COMP.get(num), tu)


def _r_sae(m, ctx):
    prefix = [ctx.p(m["org"], "American Iron and Steel Institute (Nummernsystem heute von SAE geführt)",
                    "American Iron and Steel Institute (numbering now maintained by SAE)") if m["org"] == "AISI"
              else ctx.p("SAE", "Society of Automotive Engineers", "Society of Automotive Engineers")]
    return _sae_core(ctx, m.group(0).strip(), m["num"], m["h"], m["tr"], prefix)


AISI_SS = {"201", "202", "301", "302", "303", "304", "305", "309", "310", "314", "316", "317", "321", "347", "403", "405",
           "409", "410", "416", "420", "430", "431", "434", "440"}
AISI_SS_INFO = {
    "303": ("mit Schwefel (Automatenstahl)", "with sulphur (free machining)"),
    "304": ("Standard-Chrom-Nickel-Stahl (etwa 18 % Cr, 8–10,5 % Ni)", "standard chromium-nickel grade (about 18 % Cr, 8–10.5 % Ni)"),
    "316": ("Chrom-Nickel-Stahl mit etwa 2–3 % Mo (besser beständig gegen Chloride)", "chromium-nickel grade with about 2–3 % Mo (better chloride resistance)"),
    "321": ("mit Titan stabilisiert", "titanium stabilized"),
    "347": ("mit Niob stabilisiert", "niobium stabilized"),
    "410": ("martensitischer Chromstahl (etwa 12 % Cr)", "martensitic chromium steel (about 12 % Cr)"),
    "430": ("ferritischer Chromstahl (etwa 17 % Cr)", "ferritic chromium steel (about 17 % Cr)"),
}
AISI_SS_SUF = {"L": ("niedriger Kohlenstoffgehalt (C ≤ 0,03 %), besser schweißgeeignet", "low carbon (C ≤ 0.03 %), better weldability"),
               "H": ("höherer Kohlenstoffgehalt für hohe Temperaturen", "higher carbon for high-temperature service"),
               "Ti": ("mit Titan stabilisiert", "titanium stabilized"), "N": ("mit Stickstoff legiert", "nitrogen alloyed"),
               "LN": ("niedriger Kohlenstoffgehalt, mit Stickstoff legiert", "low carbon, nitrogen alloyed")}
AISI_SS_EN = {"304": "1.4301", "304L": "1.4307", "316": "1.4401", "316L": "1.4404", "316Ti": "1.4571", "321": "1.4541", "430": "1.4016"}


def _r_aisi_ss(m, ctx):
    t = ctx.t
    num, suf = m["num"], m["suf"] or ""
    if num not in AISI_SS:
        return None
    series = {"2": ("austenitischer Chrom-Nickel-Mangan-Stahl", "austenitic chromium-nickel-manganese steel"),
              "3": ("austenitischer Chrom-Nickel-Stahl", "austenitic chromium-nickel steel"),
              "4": ("ferritischer oder martensitischer Chromstahl", "ferritic or martensitic chromium steel")}[num[0]]
    parts = []
    if m["org"]:
        parts.append(ctx.p(m["org"], "American Iron and Steel Institute (Nummernsystem heute von SAE geführt)",
                           "American Iron and Steel Institute (numbering now maintained by SAE)"))
    else:
        parts.append(ctx.p(t("ohne Vorsatz", "no prefix"), "dreistellige Zahl als AISI-Sorte nichtrostender Stähle gelesen",
                           "three-digit number read as an AISI stainless steel type"))
    parts.append(ctx.p(num, f"Reihe {num[0]}xx: {ctx.tx(series)}" + (f"; {ctx.tx(AISI_SS_INFO[num])}" if num in AISI_SS_INFO else ""),
                       f"series {num[0]}xx: {ctx.tx(series)}" + (f"; {ctx.tx(AISI_SS_INFO[num])}" if num in AISI_SS_INFO else "")))
    if suf:
        parts.append(ctx.p(suf, *AISI_SS_SUF[suf]))
    en = AISI_SS_EN.get(num + suf)
    if en:
        parts.append(ctx.p("≈ " + en, f"vergleichbare Werkstoffnummer {en} ({STEEL_NUM[en]}), nicht identisch",
                           f"comparable material number {en} ({STEEL_NUM[en]}), not identical"))
    fam = t("nichtrostender Stahl", "stainless steel")
    s = t(f"{m.group(0)}: nichtrostender Stahl, {series[0]}", f"{m.group(0)}: stainless steel, {series[1]}")
    if suf:
        s += f", {ctx.tx(AISI_SS_SUF[suf])}"
    if en:
        s += t(f" (≈ {en})", f" (≈ {en})")
    return _found(ctx, m.group(0), "AISI / SAE J405", fam, parts, s + ".", ["sae-j405"])


def _r_bare4(m, ctx):
    t = ctx.t
    num = m["num"]
    if ctx.hint == "steel":
        e = _sae_core(ctx, m.group(0).strip(), num, None, m["tr"],
                      [ctx.p(t("ohne Vorsatz", "no prefix"), "vierstellige Zahl als SAE/AISI-Stahlsorte gelesen (Werkstofffamilie Stahl)",
                             "four-digit number read as an SAE/AISI steel grade (material family steel)")])
        return e
    if ctx.hint == "al" and not m["tr"]:
        return _al_core(ctx, num, num, None, None, [ctx.p(t("ohne Vorsatz", "no prefix"), "vierstellige Zahl als Aluminium-Legierungsnummer gelesen (Werkstofffamilie Aluminium)",
                                                           "four-digit number read as an aluminium alloy number (material family aluminium)")])
    return {"_kind": "unknown", "text": m.group(0).strip(),
            "note": t(f"„{num}“ ist ohne Vorsatz mehrdeutig (z. B. EN AW-{num} oder AISI/SAE {num}).",
                      f"“{num}” is ambiguous without a prefix (e.g. EN AW-{num} or AISI/SAE {num}).")}


# ============================================================================ Gusseisen (EN 1560)
GJ_GRAPHITE = {"L": ("Lamellengraphit (Grauguss)", "lamellar graphite (grey iron)"),
               "S": ("Kugelgraphit (sphärolithisch, Sphäroguss)", "spheroidal graphite (ductile iron)"),
               "M": ("Temperkohle (Temperguss)", "temper carbon (malleable iron)"),
               "V": ("Vermiculargraphit", "vermicular (compacted) graphite"),
               "N": ("graphitfrei (Hartguss, ledeburitisch)", "graphite-free (white iron, ledeburitic)"),
               "Y": ("Sonderstruktur", "special structure")}
GJ_MICRO = {"A": ("Austenit", "austenite"), "F": ("Ferrit", "ferrite"), "P": ("Perlit", "pearlite"), "M": ("Martensit", "martensite"),
            "L": ("Ledeburit", "ledeburite"), "Q": ("abgeschreckt", "quenched"), "T": ("vergütet", "quenched and tempered"),
            "B": ("schwarz (nicht entkohlend geglüht, schwarzer Temperguss)", "black heart (non-decarburizing annealing)"),
            "W": ("weiß (entkohlend geglüht, weißer Temperguss)", "white heart (decarburizing annealing)")}


def _r_gj(m, ctx):
    t = ctx.t
    gr = m["gr"]
    parts = []
    if m["en"]:
        parts.append(ctx.p("EN", "Europäische Norm", "European Standard"))
    else:
        parts.append(ctx.p(t("ohne „EN-“", "no “EN-”"), "Kurzform ohne den Vorsatz „EN-“", "short form without the prefix “EN-”"))
    parts += [ctx.p("G", "Guss (Gusswerkstoff)", "casting"), ctx.p("J", "Eisen (J statt I, um Verwechslung mit 1 zu vermeiden)",
                                                                   "iron (J instead of I to avoid confusion with 1)"),
              ctx.p(gr, f"Graphitform: {ctx.tx(GJ_GRAPHITE[gr])}", f"graphite form: {ctx.tx(GJ_GRAPHITE[gr])}")]
    if m["mi"]:
        parts.append(ctx.p(m["mi"], f"Gefüge bzw. Behandlung: {ctx.tx(GJ_MICRO[m['mi']])}", f"matrix or treatment: {ctx.tx(GJ_MICRO[m['mi']])}"))
    txt = []
    if m["rm"]:
        parts.append(ctx.p(m["rm"], f"Mindestzugfestigkeit {m['rm']} MPa", f"minimum tensile strength {m['rm']} MPa"))
        txt.append(f"Rm ≥ {m['rm']} MPa")
    if m["hb"]:
        parts.append(ctx.p("HB" + m["hb"], f"Härte {m['hb']} HB (Sorte nach Härte statt Festigkeit)", f"hardness {m['hb']} HB (grade by hardness instead of strength)"))
        txt.append(f"{m['hb']} HB")
    if m["a"]:
        parts.append(ctx.p(m["a"], f"Mindestbruchdehnung {m['a']} %", f"minimum elongation {m['a']} %"))
        txt.append(f"A ≥ {m['a']} %")
    if m["t"]:
        tt = {"LT": ("Kerbschlagarbeit bei tiefer Temperatur festgelegt", "impact energy specified at low temperature"),
              "RT": ("Kerbschlagarbeit bei Raumtemperatur festgelegt", "impact energy specified at room temperature")}[m["t"]]
        parts.append(ctx.p(m["t"], *tt))
        txt.append(ctx.tx(tt))
    fam = {"L": t("Gusseisen mit Lamellengraphit", "grey cast iron"), "S": t("Gusseisen mit Kugelgraphit", "spheroidal graphite cast iron"),
           "M": t("Temperguss", "malleable cast iron"), "V": t("Gusseisen mit Vermiculargraphit", "compacted graphite iron"),
           "N": t("Hartguss (graphitfrei)", "white cast iron"), "Y": t("Gusseisen mit Sonderstruktur", "cast iron with special structure")}[gr]
    s = f"{m.group(0)}: {fam}" + (", " + ", ".join(txt) if txt else "") + "."
    return _found(ctx, m.group(0), "EN 1560", fam, parts, s, ["en-1560"])


# ============================================================================ Kupfer (ISO 1190-1, EN 1412, EN 1173)
CU_TYPES = {
    "ETP": ("elektrolytisch raffiniertes, sauerstoffhaltiges Kupfer (Electrolytic Tough Pitch), hohe elektrische Leitfähigkeit",
            "electrolytic tough pitch copper (oxygen-bearing), high electrical conductivity"),
    "FRHC": ("feuerraffiniertes Kupfer hoher Leitfähigkeit (Fire Refined High Conductivity)", "fire-refined high-conductivity copper"),
    "OF": ("sauerstofffreies Kupfer (Oxygen Free)", "oxygen-free copper"),
    "OFE": ("sauerstofffreies Kupfer für die Elektronik (Oxygen Free Electronic)", "oxygen-free electronic copper"),
    "DHP": ("mit Phosphor desoxidiertes Kupfer, hoher Restphosphorgehalt (Deoxidised High Phosphorus); gut schweiß- und lötbar",
            "phosphorus-deoxidized copper with high residual phosphorus; good weldability and brazeability"),
    "DLP": ("mit Phosphor desoxidiertes Kupfer, niedriger Restphosphorgehalt (Deoxidised Low Phosphorus)",
            "phosphorus-deoxidized copper with low residual phosphorus"),
    "PHC": ("mit Phosphor desoxidiertes Kupfer hoher Leitfähigkeit (Phosphorus deoxidised High Conductivity)",
            "phosphorus-deoxidized high-conductivity copper"),
    "HCP": ("Kupfer hoher Leitfähigkeit, phosphordesoxidiert (High Conductivity Phosphorus)", "high-conductivity phosphorus-deoxidized copper"),
}
CU_NUM = {"CW004A": "Cu-ETP", "CW008A": "Cu-OF", "CW024A": "Cu-DHP", "CW505L": "CuZn30", "CW508L": "CuZn37",
          "CW509L": "CuZn40", "CW614N": "CuZn39Pb3", "CW452K": "CuSn6", "CW453K": "CuSn8"}
CU_NAME = {v: k for k, v in CU_NUM.items()}
CU_COMP = {"Cu-ETP": {"Cu": "≥ 99.90", "O": "≤ 0.040"}, "CuZn37": {"Cu": "62.0–64.0", "Zn": "bal"},
           "CuSn6": {"Sn": "5.5–7.0", "P": "0.01–0.40", "Cu": "bal"}}
CU_GROUP = {"A": ("Kupfer", "copper"), "B": ("Kupfer", "copper"),
            "C": ("niedriglegierte Kupferlegierungen (< 5 % Legierungselemente)", "low-alloyed copper alloys (< 5 % alloying elements)"),
            "D": ("niedriglegierte Kupferlegierungen (< 5 % Legierungselemente)", "low-alloyed copper alloys (< 5 % alloying elements)"),
            "E": ("Sonder-Kupferlegierungen (≥ 5 % Legierungselemente)", "special copper alloys (≥ 5 % alloying elements)"),
            "F": ("Sonder-Kupferlegierungen (≥ 5 % Legierungselemente)", "special copper alloys (≥ 5 % alloying elements)"),
            "G": ("Kupfer-Aluminium-Legierungen", "copper-aluminium alloys"), "H": ("Kupfer-Nickel-Legierungen", "copper-nickel alloys"),
            "J": ("Kupfer-Nickel-Zink-Legierungen", "copper-nickel-zinc alloys"), "K": ("Kupfer-Zinn-Legierungen", "copper-tin alloys"),
            "L": ("Kupfer-Zink-Zweistofflegierungen", "binary copper-zinc alloys"), "M": ("Kupfer-Zink-Zweistofflegierungen", "binary copper-zinc alloys"),
            "N": ("Kupfer-Zink-Blei-Legierungen", "copper-zinc-lead alloys"), "P": ("Kupfer-Zink-Blei-Legierungen", "copper-zinc-lead alloys"),
            "R": ("Kupfer-Zink-Mehrstofflegierungen", "complex copper-zinc alloys"), "S": ("Kupfer-Zink-Mehrstofflegierungen", "complex copper-zinc alloys")}
CU_FORM = {"W": ("Knetwerkstoff", "wrought product"), "B": ("Blockmetall zum Umschmelzen", "ingot for remelting"),
           "C": ("Gusserzeugnis", "casting"), "F": ("Schweißzusatz bzw. Hartlot", "filler metal for welding or brazing"),
           "M": ("Vorlegierung", "master alloy"), "R": ("raffiniertes Kupfer in Rohform", "refined unwrought copper"),
           "S": ("Schrott", "scrap"), "X": ("nicht genormter Werkstoff", "non-standardized material")}
COND = r"(?:\s?(?P<cond>[RHAYBG]\d{2,4}|[DM])(?![\w]))?"


def _cu_cond(ctx, cond):
    if not cond:
        return [], ""
    k, v = cond[0], cond[1:]
    tx = {"R": (f"Mindestzugfestigkeit {v} MPa", f"minimum tensile strength {v} MPa"),
          "H": (f"Mindesthärte {v} (HV bzw. HB)", f"minimum hardness {v} (HV or HB)"),
          "A": (f"Mindestbruchdehnung {v} %", f"minimum elongation {v} %"),
          "Y": (f"Mindest-0,2-%-Dehngrenze {v} MPa", f"minimum 0.2 % proof strength {v} MPa"),
          "B": (f"Federbiegegrenze {v} MPa", f"spring bending limit {v} MPa"),
          "G": (f"Korngröße {v} µm", f"grain size {v} µm"),
          "D": ("gezogen, ohne festgelegte mechanische Eigenschaften", "drawn, without specified mechanical properties"),
          "M": ("wie gefertigt, ohne festgelegte mechanische Eigenschaften", "as manufactured, without specified mechanical properties")}[k]
    p = ctx.p(cond, f"Werkstoffzustand nach EN 1173: {ctx.tx(tx)}", f"material condition per EN 1173: {ctx.tx(tx)}")
    return [p], ctx.tx(tx)


def _cu_family(ctx, els):
    syms = [e for e, _ in els]
    t = ctx.t
    if syms and syms[0] == "Zn":
        return t("Messing (Kupfer-Zink-Legierung)", "brass (copper-zinc alloy)")
    if syms and syms[0] == "Sn":
        return t("Zinnbronze (Kupfer-Zinn-Legierung)", "tin bronze (copper-tin alloy)")
    if syms and syms[0] == "Al":
        return t("Aluminiumbronze (Kupfer-Aluminium-Legierung)", "aluminium bronze (copper-aluminium alloy)")
    if syms and syms[0] == "Ni" and "Zn" in syms:
        return t("Neusilber (Kupfer-Nickel-Zink-Legierung)", "nickel silver (copper-nickel-zinc alloy)")
    if syms and syms[0] == "Ni":
        return t("Kupfer-Nickel-Legierung", "copper-nickel alloy")
    return t("Kupferlegierung", "copper alloy")


def _r_cu_type(m, ctx):
    t = ctx.t
    ty = m["ty"]
    parts = [ctx.p("Cu", "Kupfer (unlegiert)", "copper (unalloyed)"), ctx.p(ty, *CU_TYPES[ty])]
    cp, ctxt = _cu_cond(ctx, m["cond"])
    parts += cp
    name = "Cu-" + ty
    refs = ["iso-1190-1"] + (["en-1173"] if cp else [])
    if name in CU_NAME:
        parts.append(ctx.p("≙ " + CU_NAME[name], f"Werkstoffnummer nach EN 1412: {CU_NAME[name]}", f"material number per EN 1412: {CU_NAME[name]}"))
        refs.append("en-1412")
    fam = t("Kupfer (unlegiert)", "copper (unalloyed)")
    s = t(f"{m.group(0)}: unlegiertes Kupfer, {CU_TYPES[ty][0]}", f"{m.group(0)}: unalloyed copper, {CU_TYPES[ty][1]}")
    if ctxt:
        s += t(f"; Zustand: {ctxt}", f"; condition: {ctxt}")
    return _found(ctx, m.group(0), "ISO 1190-1 / EN 1173" if cp else "ISO 1190-1", fam, parts, s + ".", refs, CU_COMP.get(name))


CU_EL = ["Zn", "Sn", "Al", "Ni", "Pb", "Fe", "Mn", "Si", "Be", "Co", "Cr", "Zr", "Ag", "Te", "Mg", "Cd", "As", "Bi", "Ti", "P", "S"]


def _r_cu_chem(m, ctx):
    t = ctx.t
    els = _el_list(m["body"], CU_EL)
    if not els:
        return None
    parts = [ctx.p("Cu", "Basismetall Kupfer (Rest)", "base metal copper (balance)")] + _chem_parts(ctx, els, "", "")
    cp, ctxt = _cu_cond(ctx, m["cond"])
    parts += cp
    name = "Cu" + m["body"]
    refs = ["iso-1190-1"] + (["en-1173"] if cp else [])
    if name in CU_NAME:
        parts.append(ctx.p("≙ " + CU_NAME[name], f"Werkstoffnummer nach EN 1412: {CU_NAME[name]}", f"material number per EN 1412: {CU_NAME[name]}"))
        refs.append("en-1412")
    fam = _cu_family(ctx, els)
    first = els[0]
    s = t(f"{m.group(0)}: {fam}", f"{m.group(0)}: {fam}")
    if first[1]:
        s += t(f" mit etwa {ctx.num(first[1])} % {ctx.el(first[0])}", f" with about {ctx.num(first[1])} % {ctx.el(first[0])}")
    if ctxt:
        s += t(f"; Zustand: {ctxt}", f"; condition: {ctxt}")
    return _found(ctx, m.group(0), "ISO 1190-1 / EN 1173" if cp else "ISO 1190-1", fam, parts, s + ".", refs, CU_COMP.get(name))


def _r_cu_num(m, ctx):
    t = ctx.t
    form, n, g = m["f"], m["n"], m["g"]
    parts = [ctx.p("C", "Kupferwerkstoff", "copper material"), ctx.p(form, *CU_FORM[form]),
             ctx.p(n, "Zählnummer", "sequential number"), ctx.p(g, f"Werkstoffgruppe: {ctx.tx(CU_GROUP[g])}", f"material group: {ctx.tx(CU_GROUP[g])}")]
    cp, ctxt = _cu_cond(ctx, m["cond"])
    parts += cp
    code = f"C{form}{n}{g}"
    name = CU_NUM.get(code)
    refs = ["en-1412"] + (["en-1173"] if cp else [])
    if name:
        parts.append(ctx.p("≙ " + name, f"Kurzzeichen: {name}", f"symbol designation: {name}"))
        refs.append("iso-1190-1")
    fam = ctx.tx(CU_GROUP[g])
    s = t(f"{m.group(0)}: Werkstoffnummer eines Kupferwerkstoffs ({CU_FORM[form][0]}, {CU_GROUP[g][0]})",
          f"{m.group(0)}: material number of a copper material ({CU_FORM[form][1]}, {CU_GROUP[g][1]})")
    if name:
        s += t(f", Kurzzeichen {name}", f", symbol {name}")
    if ctxt:
        s += t(f"; Zustand: {ctxt}", f"; condition: {ctxt}")
    return _found(ctx, m.group(0), "EN 1412" + (" / EN 1173" if cp else ""), fam, parts, s + ".", refs, CU_COMP.get(name) if name else None)


def _r_ms(m, ctx):
    t = ctx.t
    cu = int(m["n"])
    if not 55 <= cu <= 95:
        return None
    new = {63: "CuZn37", 70: "CuZn30", 60: "CuZn40"}.get(cu)
    parts = [ctx.p("Ms", "Messing (Kupfer-Zink-Legierung), alte DIN-Bezeichnung", "brass (copper-zinc alloy), former DIN designation"),
             ctx.p(m["n"], f"Kupfergehalt etwa {cu} % (Rest im Wesentlichen Zink)", f"copper content about {cu} % (balance essentially zinc)")]
    if new:
        parts.append(ctx.p("≙ " + new, f"heutige Bezeichnung: {new}", f"current designation: {new}"))
    s = t(f"{m.group(0)}: alte Bezeichnung (DIN 17660) für Messing mit etwa {cu} % Cu", f"{m.group(0)}: former designation (DIN 17660) of brass with about {cu} % Cu")
    s += (t(f", heute {new}", f", today {new}") if new else "") + "."
    return _found(ctx, m.group(0), "DIN 17660 " + t("(zurückgezogen)", "(withdrawn)"), t("Messing", "brass"), parts, s,
                  ["din-17660"] + (["iso-1190-1"] if new else []))


# ============================================================================ Titan (ASTM B265/B348)
TI_GRADES = {
    "1": ("Reintitan mit dem niedrigsten Sauerstoffgehalt (O ≤ 0,18 %), geringste Festigkeit (Rm ≥ 240 MPa), beste Umformbarkeit",
          "unalloyed titanium with the lowest oxygen content (O ≤ 0.18 %), lowest strength (Rm ≥ 240 MPa), best formability", "3.7025", "R50250"),
    "2": ("Reintitan (O ≤ 0,25 %), Rm ≥ 345 MPa", "unalloyed titanium (O ≤ 0.25 %), Rm ≥ 345 MPa", "3.7035", "R50400"),
    "3": ("Reintitan (O ≤ 0,35 %), Rm ≥ 450 MPa", "unalloyed titanium (O ≤ 0.35 %), Rm ≥ 450 MPa", "3.7055", "R50550"),
    "4": ("Reintitan mit dem höchsten Sauerstoffgehalt (O ≤ 0,40 %), höchste Festigkeit der Reintitansorten (Rm ≥ 550 MPa)",
          "unalloyed titanium with the highest oxygen content (O ≤ 0.40 %), highest strength of the unalloyed grades (Rm ≥ 550 MPa)", "3.7065", "R50700"),
    "5": ("Titanlegierung Ti-6Al-4V (α+β-Legierung, etwa 6 % Al und 4 % V)", "titanium alloy Ti-6Al-4V (alpha-beta alloy, about 6 % Al and 4 % V)",
          "3.7165", "R56400"),
    "7": ("Reintitan wie Grade 2 mit 0,12–0,25 % Palladium (bessere Korrosionsbeständigkeit)",
          "unalloyed titanium like grade 2 with 0.12–0.25 % palladium (better corrosion resistance)", None, None),
    "9": ("Titanlegierung Ti-3Al-2,5V", "titanium alloy Ti-3Al-2.5V", None, None),
    "11": ("Reintitan wie Grade 1 mit 0,12–0,25 % Palladium", "unalloyed titanium like grade 1 with 0.12–0.25 % palladium", None, None),
    "12": ("Titanlegierung Ti-0,3Mo-0,8Ni", "titanium alloy Ti-0.3Mo-0.8Ni", None, None),
    "23": ("Ti-6Al-4V ELI (Extra Low Interstitials: weniger O, N, C und Fe; höhere Zähigkeit, u. a. für Implantate)",
           "Ti-6Al-4V ELI (extra low interstitials: less O, N, C and Fe; higher toughness, e.g. for implants)", None, None),
}
TI_COMP = {"1": {"O": "≤ 0.18", "Fe": "≤ 0.20"}, "2": {"O": "≤ 0.25", "Fe": "≤ 0.30"}, "3": {"O": "≤ 0.35", "Fe": "≤ 0.30"},
           "4": {"O": "≤ 0.40", "Fe": "≤ 0.50"}, "5": {"Al": "5.5–6.75", "V": "3.5–4.5", "Fe": "≤ 0.40", "O": "≤ 0.20"}}
TI_EL = ["Al", "V", "Mo", "Sn", "Zr", "Nb", "Cr", "Fe", "Pd", "Ni", "Si", "Ta"]


def _r_ti_grade(m, ctx):
    t = ctx.t
    g = m["g"]
    if g not in TI_GRADES:
        return None
    de, en, din, uns = TI_GRADES[g]
    parts = []
    if m["ti"]:
        parts.append(ctx.p(m["ti"], "Werkstoff Titan", "material titanium"))
    parts.append(ctx.p(f"Grade {g}", t(de, en) + t(" (Sortenbezeichnung nach ASTM B265/B348)", " (grade per ASTM B265/B348)"),
                       t(de, en) + t(" (Sortenbezeichnung nach ASTM B265/B348)", " (grade per ASTM B265/B348)")))
    if m["eli"]:
        parts.append(ctx.p("ELI", "Extra Low Interstitials (verringerte Gehalte an O, N, C, Fe)", "extra low interstitials (reduced O, N, C, Fe)"))
    if din:
        parts.append(ctx.p("≙ " + din, f"Werkstoffnummer nach DIN 17007-4: {din}", f"material number per DIN 17007-4: {din}"))
    if uns:
        parts.append(ctx.p("≙ UNS " + uns, f"UNS-Nummer {uns}", f"UNS number {uns}"))
    fam = t("Reintitan", "commercially pure titanium") if g in ("1", "2", "3", "4", "7", "11") else t("Titanlegierung", "titanium alloy")
    s = t(f"{m.group(0)}: {de}.", f"{m.group(0)}: {en}.")
    refs = ["astm-b265", "astm-b348"] + (["din-17007-4"] if din else []) + (["astm-e527"] if uns else [])
    return _found(ctx, m.group(0), "ASTM B265 / B348", fam, parts, s, refs, TI_COMP.get(g))


def _r_ti_alloy(m, ctx):
    t = ctx.t
    items = re.findall(r"(\d+(?:[.,]\d+)?)([A-Z][a-z]?)", m["body"])
    if not items or any(e not in TI_EL for _, e in items):
        return None
    parts = [ctx.p("Ti", "Basismetall Titan (Rest)", "base metal titanium (balance)")]
    for n, e in items:
        parts.append(ctx.p(n + e, f"{ctx.el(e)} etwa {ctx.num(n)} % (Massenanteil)", f"{ctx.el(e)} about {ctx.num(n)} % (by mass)"))
    if m["eli"]:
        parts.append(ctx.p("ELI", "Extra Low Interstitials (verringerte Gehalte an O, N, C, Fe)", "extra low interstitials (reduced O, N, C, Fe)"))
    body = m["body"].replace(",", ".")
    grade = {"6Al-4V": "23" if m["eli"] else "5", "3Al-2.5V": "9"}.get(body)
    refs = ["astm-b265"]
    if grade:
        parts.append(ctx.p(f"≙ Grade {grade}", f"entspricht ASTM Grade {grade}", f"corresponds to ASTM grade {grade}"))
        if grade == "5":
            parts.append(ctx.p("≙ 3.7165", "Werkstoffnummer nach DIN 17007-4: 3.7165", "material number per DIN 17007-4: 3.7165"))
            refs.append("din-17007-4")
    fam = t("Titanlegierung", "titanium alloy")
    s = t(f"{m.group(0)}: Titanlegierung mit ", f"{m.group(0)}: titanium alloy with ") + ", ".join(f"{ctx.num(n)} % {e}" for n, e in items)
    if grade:
        s += f" (ASTM Grade {grade})"
    return _found(ctx, m.group(0), t("Elementschreibweise (ASTM B265)", "element notation (ASTM B265)"), fam, parts, s + ".", refs,
                  TI_COMP.get(grade) if grade == "5" else None)


def _r_ti64(m, ctx):
    t = ctx.t
    parts = [ctx.p("Ti64", "gebräuchliche Kurzform für Ti-6Al-4V (keine Normbezeichnung)", "common short form of Ti-6Al-4V (not a standard designation)"),
             ctx.p("≙ Grade 5", "entspricht ASTM Grade 5", "corresponds to ASTM grade 5")]
    return _found(ctx, m.group(0), t("Kurzform", "short form"), t("Titanlegierung", "titanium alloy"), parts,
                  t("Ti64: Kurzform für die Titanlegierung Ti-6Al-4V (Grade 5).", "Ti64: short form of the titanium alloy Ti-6Al-4V (grade 5)."),
                  ["astm-b265"])


# ============================================================================ Magnesium (ASTM B275, B296)
MG_CODES = {"A": "Al", "B": "Bi", "C": "Cu", "D": "Cd", "E": None, "F": "Fe", "H": "Th", "J": "Sr", "K": "Zr", "L": "Li", "M": "Mn",
            "N": "Ni", "P": "Pb", "Q": "Ag", "R": "Cr", "S": "Si", "T": "Sn", "W": "Y", "X": "Ca", "Y": "Sb", "Z": "Zn"}
MG_COMP = {"AZ31B": {"Al": "2.5–3.5", "Zn": "0.6–1.4", "Mn": "0.20–1.0"}}


def _mg_name(ctx, letter):
    sym = MG_CODES[letter]
    return ctx.t("Seltene Erden", "rare earths") if sym is None else ctx.el(sym)


def _r_mg(m, ctx):
    t = ctx.t
    a, b = m["a"], m["b"]
    if a not in MG_CODES or b not in MG_CODES:
        return None
    if not (m["s"] or m["temp"] or ctx.hint == "mg"):
        return None
    parts = [ctx.p(a, f"wichtigstes Legierungselement: {_mg_name(ctx, a)}", f"main alloying element: {_mg_name(ctx, a)}"),
             ctx.p(b, f"zweitwichtigstes Legierungselement: {_mg_name(ctx, b)}", f"second alloying element: {_mg_name(ctx, b)}"),
             ctx.p(m["x"], f"{_mg_name(ctx, a)} gerundet etwa {m['x']} %", f"{_mg_name(ctx, a)} rounded to about {m['x']} %"),
             ctx.p(m["y"], f"{_mg_name(ctx, b)} gerundet etwa {m['y']} %", f"{_mg_name(ctx, b)} rounded to about {m['y']} %")]
    if m["s"]:
        if m["s"] == "X":
            parts.append(ctx.p("X", "Versuchslegierung (noch nicht genormt)", "experimental alloy (not yet standardized)"))
        else:
            k = "ABCDE".index(m["s"]) + 1
            parts.append(ctx.p(m["s"], f"Kennbuchstabe für die {k}. genormte Variante dieser Nennzusammensetzung",
                               f"letter for the {k}{'st' if k == 1 else 'nd' if k == 2 else 'rd' if k == 3 else 'th'} standardized variant of this nominal composition"))
    unk = []
    tparts = []
    if m["temp"]:
        tparts, unk = _tempers(m["temp"], ctx, mg=True)
        parts += tparts
    code = f"{a}{b}{m['x']}{m['y']}{m['s'] or ''}"
    refs = ["astm-b275"] + (["astm-b296"] if m["temp"] else []) + (["astm-b90"] if code in MG_COMP else [])
    fam = t("Magnesiumlegierung", "magnesium alloy")
    s = t(f"{m.group(0)}: Magnesiumlegierung mit etwa {m['x']} % {_mg_name(ctx, a)} und {m['y']} % {_mg_name(ctx, b)}",
          f"{m.group(0)}: magnesium alloy with about {m['x']} % {_mg_name(ctx, a)} and {m['y']} % {_mg_name(ctx, b)}")
    if tparts:
        s += t(f", Zustand {m['temp']}: {_temper_text(tparts)}", f", temper {m['temp']}: {_temper_text(tparts)}")
    return _found(ctx, m.group(0), "ASTM B275" + (" / B296" if m["temp"] else ""), fam, parts, s + ".", refs, MG_COMP.get(code), unk)


# ============================================================================ Nickel, UNS, DIN-Werkstoffnummern 2.x/3.x
NI_ALLOYS = {
    "200": ("Nickel", "N02200", "Ni 99,2", "2.4066", ("handelsübliches Reinnickel (Ni ≥ 99,0 %)", "commercially pure nickel (Ni ≥ 99.0 %)"), "astm-b162",
            {"Ni": "≥ 99.0", "Fe": "≤ 0.40", "Cu": "≤ 0.25", "C": "≤ 0.15"}),
    "201": ("Nickel", "N02201", "LC-Ni 99", "2.4068", ("Reinnickel mit niedrigem Kohlenstoffgehalt", "low-carbon commercially pure nickel"), "astm-b162", None),
    "400": ("Monel", "N04400", "NiCu30Fe", "2.4360", ("Nickel-Kupfer-Legierung (etwa 30 % Cu)", "nickel-copper alloy (about 30 % Cu)"), None, None),
    "600": ("Inconel", "N06600", "NiCr15Fe", "2.4816", ("Nickel-Chrom-Eisen-Legierung", "nickel-chromium-iron alloy"), None, None),
    "625": ("Inconel", "N06625", "NiCr22Mo9Nb", "2.4856",
            ("mischkristallverfestigte Nickel-Chrom-Molybdän-Niob-Legierung", "solid-solution strengthened nickel-chromium-molybdenum-niobium alloy"),
            "astm-b443", {"Ni": "≥ 58.0", "Cr": "20.0–23.0", "Mo": "8.0–10.0", "Nb+Ta": "3.15–4.15", "Fe": "≤ 5.0"}),
    "718": ("Inconel", "N07718", "NiCr19Fe19Nb5Mo3", "2.4668",
            ("ausscheidungshärtbare Nickel-Chrom-Eisen-Legierung mit Niob und Molybdän", "precipitation-hardenable nickel-chromium-iron alloy with niobium and molybdenum"),
            "astm-b637", {"Ni": "50.0–55.0", "Cr": "17.0–21.0", "Nb+Ta": "4.75–5.50", "Mo": "2.80–3.30", "Ti": "0.65–1.15",
                          "Al": "0.20–0.80", "Fe": "bal"}),
    "C-276": ("Hastelloy", "N10276", "NiMo16Cr15W", "2.4819", ("Nickel-Molybdän-Chrom-Legierung", "nickel-molybdenum-chromium alloy"), None, None),
}
TRADE_OWNER = {"Inconel": "Special Metals Corporation", "Monel": "Special Metals Corporation", "Hastelloy": "Haynes International"}


def _r_ni(m, ctx):
    t = ctx.t
    brand, n = m["b"], m["n"]
    if n not in NI_ALLOYS:
        return None
    family_name, uns, din_name, din_num, desc, ref, comp = NI_ALLOYS[n]
    if brand not in ("Alloy", family_name):
        return None
    parts = []
    if brand == "Alloy":
        parts.append(ctx.p("Alloy", "herstellerneutrale Bezeichnung (statt des Handelsnamens)", "generic designation (instead of the trade name)"))
    elif brand in TRADE_OWNER:
        parts.append(ctx.p(brand, f"Handelsname ({TRADE_OWNER[brand]}), keine Normbezeichnung",
                           f"trade name ({TRADE_OWNER[brand]}), not a standard designation"))
    else:
        parts.append(ctx.p(brand, "Werkstoff Nickel (handelsübliche Bezeichnung)", "material nickel (commercial designation)"))
    parts.append(ctx.p(n, f"Sortennummer: {ctx.tx(desc)}", f"grade number: {ctx.tx(desc)}"))
    parts.append(ctx.p("≙ UNS " + uns, f"UNS-Nummer {uns} (N = Nickel und Nickellegierungen)", f"UNS number {uns} (N = nickel and nickel alloys)"))
    parts.append(ctx.p("≙ " + din_num, f"DIN-Werkstoffnummer {din_num}, Kurzzeichen {din_name}", f"DIN material number {din_num}, symbol {din_name}"))
    refs = ["astm-e527", "din-17742" if din_name.startswith("NiCr") else "din-17740"] + ([ref] if ref else []) + ["din-17007-4"]
    fam = t("Reinnickel", "commercially pure nickel") if n in ("200", "201") else t("Nickellegierung", "nickel alloy")
    s = t(f"{m.group(0)}: {ctx.tx(desc)}, UNS {uns}, Werkstoffnummer {din_num} ({din_name})",
          f"{m.group(0)}: {ctx.tx(desc)}, UNS {uns}, material number {din_num} ({din_name})")
    if brand in TRADE_OWNER:
        s += t(f"; „{brand}“ ist ein Handelsname von {TRADE_OWNER[brand]}", f"; “{brand}” is a trade name of {TRADE_OWNER[brand]}")
    return _found(ctx, m.group(0), "UNS / " + t("Handelsname", "trade name"), fam, parts, s + ".", refs, comp)


def _r_ni_pure(m, ctx):
    t = ctx.t
    p = m["p"]
    parts = [ctx.p("Ni", "Nickel (unlegiert)", "nickel (unalloyed)"),
             ctx.p(p, f"Nickelgehalt {ctx.num(p)} % (Nennwert der Sorte)", f"nickel content {ctx.num(p)} % (nominal value of the grade)")]
    if p.replace(".", ",") == "99,2":
        parts.append(ctx.p("≙ 2.4066", "Werkstoffnummer 2.4066, entspricht Nickel 200 (UNS N02200)", "material number 2.4066, corresponds to Nickel 200 (UNS N02200)"))
    return _found(ctx, m.group(0), "DIN 17740", t("Reinnickel", "commercially pure nickel"), parts,
                  t(f"{m.group(0)}: Reinnickel mit {ctx.num(p)} % Ni.", f"{m.group(0)}: commercially pure nickel with {ctx.num(p)} % Ni."), ["din-17740"])


NI_EL = ["Cr", "Mo", "Fe", "Cu", "Co", "Nb", "Ti", "Al", "W", "Mn", "Si", "Ta"]


def _r_ni_chem(m, ctx):
    t = ctx.t
    els = _el_list(m["body"], NI_EL)
    if not els:
        return None
    parts = [ctx.p("Ni", "Basismetall Nickel", "base metal nickel")] + _chem_parts(ctx, els, "", "")
    name = "Ni" + m["body"]
    hit = [(n, v) for n, v in NI_ALLOYS.items() if v[2] == name]
    if hit:
        n, v = hit[0]
        parts.append(ctx.p("≙ " + v[3], f"Werkstoffnummer {v[3]}, UNS {v[1]} ({v[0]} {n})", f"material number {v[3]}, UNS {v[1]} ({v[0]} {n})"))
    ref = "din-17742" if els[0][0] == "Cr" else "din-17740"
    return _found(ctx, m.group(0), "DIN 17740/17742", t("Nickellegierung", "nickel alloy"), parts,
                  t(f"{m.group(0)}: Nickellegierung, Bezeichnung nach chemischer Zusammensetzung.",
                    f"{m.group(0)}: nickel alloy, designation by chemical composition."), [ref])


UNS_LETTER = {"A": ("Aluminium und Aluminiumlegierungen", "aluminium and aluminium alloys"), "C": ("Kupfer und Kupferlegierungen", "copper and copper alloys"),
              "E": ("Seltene Erden und verwandte Metalle", "rare earth and similar metals"), "F": ("Gusseisen", "cast irons"),
              "G": ("AISI/SAE-Kohlenstoff- und legierte Stähle", "AISI and SAE carbon and alloy steels"), "H": ("AISI/SAE-H-Stähle", "AISI and SAE H-steels"),
              "J": ("Stahlguss", "cast steels"), "K": ("sonstige Stähle", "miscellaneous steels"), "L": ("niedrigschmelzende Metalle", "low-melting metals"),
              "M": ("sonstige Nichteisenmetalle", "miscellaneous nonferrous metals"), "N": ("Nickel und Nickellegierungen", "nickel and nickel alloys"),
              "P": ("Edelmetalle", "precious metals"), "R": ("reaktive und hochschmelzende Metalle", "reactive and refractory metals"),
              "S": ("hitze- und korrosionsbeständige Stähle", "heat and corrosion resistant steels"), "T": ("Werkzeugstähle", "tool steels"),
              "W": ("Schweißzusätze", "welding filler metals"), "Z": ("Zink und Zinklegierungen", "zinc and zinc alloys")}
UNS_KNOWN = {"N02200": "Nickel 200", "N02201": "Nickel 201", "N04400": "Monel 400", "N06600": "Inconel 600", "N06625": "Inconel 625",
             "N07718": "Inconel 718", "N10276": "Hastelloy C-276", "S30400": "AISI 304", "S30403": "AISI 304L", "S31600": "AISI 316",
             "S31603": "AISI 316L", "S31635": "AISI 316Ti", "S32100": "AISI 321", "S43000": "AISI 430", "G10200": "SAE 1020",
             "G10400": "SAE 1040", "G41400": "SAE 4140", "G43400": "SAE 4340", "R50250": "Ti Grade 1", "R50400": "Ti Grade 2",
             "R50550": "Ti Grade 3", "R50700": "Ti Grade 4", "R56400": "Ti-6Al-4V (Grade 5)", "M11311": "AZ31B", "A92024": "2024",
             "A95052": "5052", "A96061": "6061", "A97075": "7075", "C11000": "Cu-ETP"}


def _r_uns(m, ctx):
    t = ctx.t
    L, n = m["l"], m["n"]
    if L not in UNS_LETTER:
        return None
    code = L + n
    parts = [ctx.p("UNS", "Unified Numbering System (ASTM E527 / SAE J1086)", "Unified Numbering System (ASTM E527 / SAE J1086)"),
             ctx.p(L, f"Werkstoffgruppe: {ctx.tx(UNS_LETTER[L])}", f"material group: {ctx.tx(UNS_LETTER[L])}"),
             ctx.p(n, "fünfstellige Nummer innerhalb der Gruppe", "five-digit number within the group")]
    if code in UNS_KNOWN:
        parts.append(ctx.p("≙ " + UNS_KNOWN[code], f"entspricht {UNS_KNOWN[code]}", f"corresponds to {UNS_KNOWN[code]}"))
    s = t(f"{m.group(0)}: UNS-Nummer, Gruppe {UNS_LETTER[L][0]}", f"{m.group(0)}: UNS number, group {UNS_LETTER[L][1]}")
    if code in UNS_KNOWN:
        s += f" ({UNS_KNOWN[code]})"
    return _found(ctx, m.group(0), "UNS (ASTM E527)", ctx.tx(UNS_LETTER[L]), parts, s + ".", ["astm-e527"])


DIN_NF = {"2.4066": ("Ni 99,2", "Nickel 200"), "2.4068": ("LC-Ni 99", "Nickel 201"), "2.4360": ("NiCu30Fe", "Monel 400"),
          "2.4816": ("NiCr15Fe", "Inconel 600"), "2.4856": ("NiCr22Mo9Nb", "Inconel 625 / Alloy 625"),
          "2.4668": ("NiCr19Fe19Nb5Mo3", "Inconel 718 / Alloy 718"), "2.4819": ("NiMo16Cr15W", "Hastelloy C-276"),
          "3.7025": ("Ti1", "Titan Grade 1"), "3.7035": ("Ti2", "Titan Grade 2"), "3.7055": ("Ti3", "Titan Grade 3"),
          "3.7065": ("Ti4", "Titan Grade 4"), "3.7165": ("TiAl6V4", "Ti-6Al-4V (Grade 5)"), "3.5312": ("MgAl3Zn1", "AZ31")}


def _r_din_nf(m, ctx):
    t = ctx.t
    main, sub, rest = m["h"], m["s"], m["r"]
    num = f"{main}.{sub}{rest}"
    groups = {("2", "0"): ("Kupfer und Kupferlegierungen", "copper and copper alloys", "cu"),
              ("2", "1"): ("Kupfer und Kupferlegierungen", "copper and copper alloys", "cu"),
              ("2", "4"): ("Nickel, Cobalt und ihre Legierungen", "nickel, cobalt and their alloys", "ni"),
              ("3", "0"): ("Aluminium und Aluminiumlegierungen", "aluminium and aluminium alloys", "al"),
              ("3", "1"): ("Aluminium und Aluminiumlegierungen", "aluminium and aluminium alloys", "al"),
              ("3", "2"): ("Aluminium und Aluminiumlegierungen", "aluminium and aluminium alloys", "al"),
              ("3", "3"): ("Aluminium und Aluminiumlegierungen", "aluminium and aluminium alloys", "al"),
              ("3", "4"): ("Aluminium und Aluminiumlegierungen", "aluminium and aluminium alloys", "al"),
              ("3", "5"): ("Magnesium und Magnesiumlegierungen", "magnesium and magnesium alloys", "mg"),
              ("3", "7"): ("Titan und Titanlegierungen", "titanium and titanium alloys", "ti")}
    g = groups.get((main, sub))
    if not g:
        return None
    parts = [ctx.p(main, *(("Werkstoffhauptgruppe 2: Schwermetalle außer Eisen", "material main group 2: heavy metals except iron") if main == "2"
                           else ("Werkstoffhauptgruppe 3: Leichtmetalle", "material main group 3: light metals"))),
             ctx.p(sub, f"Sortenklasse: {ctx.t(g[0], g[1])}", f"alloy class: {ctx.t(g[0], g[1])}"),
             ctx.p(rest, "Zählnummer", "sequential number")]
    unk = []
    tparts = []
    if m["temp"]:
        if g[2] not in ("al", "mg"):
            return None
        tparts, unk = _tempers(m["temp"], ctx, mg=(g[2] == "mg"))
        parts += tparts
    known = DIN_NF.get(num)
    if known:
        parts.append(ctx.p("≙ " + known[0], f"Kurzzeichen {known[0]} ({known[1]})", f"symbol {known[0]} ({known[1]})"))
    s = t(f"{m.group(0)}: DIN-Werkstoffnummer, {g[0]}", f"{m.group(0)}: DIN material number, {g[1]}")
    if known:
        s += f" ({known[0]}, {known[1]})"
    if tparts:
        s += t(f", Zustand {m['temp']}: {_temper_text(tparts)}", f", temper {m['temp']}: {_temper_text(tparts)}")
    refs = ["din-17007-4"] + ((["en-515"] if g[2] == "al" else ["astm-b296"]) if tparts else [])
    return _found(ctx, m.group(0), "DIN 17007-4", ctx.t(g[0], g[1]), parts, s + ".", refs, None, unk)


# ============================================================================ Kunststoffe (ISO 1043-1/-2)
POLY = {
    "ABS": ("Acrylnitril-Butadien-Styrol", "acrylonitrile-butadiene-styrene", "T"),
    "ASA": ("Acrylnitril-Styrol-Acrylester", "acrylonitrile-styrene-acrylate", "T"),
    "EP": ("Epoxidharz", "epoxy resin", "D"),
    "MF": ("Melamin-Formaldehyd-Harz", "melamine-formaldehyde resin", "D"),
    "PAI": ("Polyamidimid", "polyamide-imide", "T"),
    "PBT": ("Polybutylenterephthalat", "poly(butylene terephthalate)", "T"),
    "PC": ("Polycarbonat", "polycarbonate", "T"),
    "PE": ("Polyethylen", "polyethylene", "T"),
    "PEEK": ("Polyetheretherketon", "polyetheretherketone", "T"),
    "PEI": ("Polyetherimid", "polyetherimide", "T"),
    "PES": ("Polyethersulfon", "polyethersulfone", "T"),
    "PET": ("Polyethylenterephthalat", "poly(ethylene terephthalate)", "T"),
    "PF": ("Phenol-Formaldehyd-Harz", "phenol-formaldehyde resin", "D"),
    "PI": ("Polyimid", "polyimide", "H"),
    "PLA": ("Polylactid (Polymilchsäure)", "polylactide (poly(lactic acid))", "T"),
    "PMMA": ("Polymethylmethacrylat (Acrylglas)", "poly(methyl methacrylate) (acrylic glass)", "T"),
    "POM": ("Polyoxymethylen (Polyacetal)", "polyoxymethylene (polyacetal)", "T"),
    "PP": ("Polypropylen", "polypropylene", "T"),
    "PPS": ("Polyphenylensulfid", "poly(phenylene sulfide)", "T"),
    "PS": ("Polystyrol", "polystyrene", "T"),
    "PSU": ("Polysulfon", "polysulfone", "T"),
    "PTFE": ("Polytetrafluorethylen", "polytetrafluoroethylene", "T"),
    "PUR": ("Polyurethan", "polyurethane", "K"),
    "PVC": ("Polyvinylchlorid", "poly(vinyl chloride)", "T"),
    "PVDF": ("Polyvinylidenfluorid", "poly(vinylidene fluoride)", "T"),
    "SAN": ("Styrol-Acrylnitril", "styrene-acrylonitrile", "T"),
    "UF": ("Harnstoff-Formaldehyd-Harz", "urea-formaldehyde resin", "D"),
    "UP": ("ungesättigtes Polyesterharz", "unsaturated polyester resin", "D"),
}
POLY_NONISO = {
    "PETG": ("glykolmodifiziertes Polyethylenterephthalat (G = glykolmodifiziert); gebräuchliches Kurzzeichen, nicht in ISO 1043-1",
             "glycol-modified poly(ethylene terephthalate) (G = glycol-modified); common abbreviation, not in ISO 1043-1", "T"),
    "GPPS": ("Standard-Polystyrol (General Purpose Polystyrene); gebräuchliches Kurzzeichen, nicht in ISO 1043-1",
             "general purpose polystyrene; common abbreviation, not in ISO 1043-1", "T"),
    "HIPS": ("schlagzähes Polystyrol (High Impact Polystyrene); gebräuchliches Kurzzeichen, nicht in ISO 1043-1",
             "high impact polystyrene; common abbreviation, not in ISO 1043-1", "T"),
}
POLY_FAM = {"T": ("Thermoplast", "thermoplastic"), "D": ("Duroplast (Reaktionsharz)", "thermoset (reaction resin)"),
            "H": ("Hochleistungskunststoff", "high-performance polymer"), "K": ("Kunststoff", "plastic")}
POLY_SUF = {
    "PE": {"HD": ("hohe Dichte (High Density)", "high density"), "LD": ("niedrige Dichte (Low Density)", "low density"),
           "LLD": ("lineare niedrige Dichte (Linear Low Density)", "linear low density"), "MD": ("mittlere Dichte", "medium density"),
           "UHMW": ("ultrahohe Molmasse (Ultra High Molecular Weight)", "ultra-high molecular weight"),
           "HMW": ("hohe Molmasse", "high molecular weight"), "X": ("vernetzt", "cross-linked")},
    "PP": {"H": ("Homopolymer", "homopolymer"), "B": ("Block-Copolymer (schlagzäh)", "block copolymer (impact modified)"),
           "R": ("Random-Copolymer (statistisches Copolymer)", "random copolymer")},
    "PVC": {"U": ("weichmacherfrei (Hart-PVC)", "unplasticized (rigid PVC)"), "P": ("weichmacherhaltig (Weich-PVC)", "plasticized (flexible PVC)"),
            "C": ("chloriert", "chlorinated")},
    "POM": {"C": ("Copolymer (gebräuchliche Kennzeichnung, kein ISO-1043-1-Zusatzzeichen)", "copolymer (common marking, not an ISO 1043-1 symbol)"),
            "H": ("Homopolymer (gebräuchliche Kennzeichnung, kein ISO-1043-1-Zusatzzeichen)", "homopolymer (common marking, not an ISO 1043-1 symbol)")},
}
PA_TYPES = {
    "6": ("aus ε-Caprolactam (ein Baustein mit 6 C-Atomen)", "from ε-caprolactam (one monomer with 6 carbon atoms)"),
    "11": ("aus 11-Aminoundecansäure (11 C-Atome)", "from 11-aminoundecanoic acid (11 carbon atoms)"),
    "12": ("aus Laurinlactam (12 C-Atome)", "from laurolactam (12 carbon atoms)"),
    "46": ("aus Tetramethylendiamin (4 C) und Adipinsäure (6 C)", "from tetramethylenediamine (4 C) and adipic acid (6 C)"),
    "66": ("aus Hexamethylendiamin (6 C) und Adipinsäure (6 C)", "from hexamethylenediamine (6 C) and adipic acid (6 C)"),
    "610": ("aus Hexamethylendiamin (6 C) und Sebacinsäure (10 C)", "from hexamethylenediamine (6 C) and sebacic acid (10 C)"),
    "612": ("aus Hexamethylendiamin (6 C) und Dodecandisäure (12 C)", "from hexamethylenediamine (6 C) and dodecanedioic acid (12 C)"),
    "1010": ("aus Decamethylendiamin (10 C) und Sebacinsäure (10 C)", "from decamethylenediamine (10 C) and sebacic acid (10 C)"),
}
FILL_MAT = {"G": ("Glas", "glass"), "C": ("Kohlenstoff", "carbon"), "M": ("Mineral", "mineral"), "K": ("Kreide", "calcium carbonate (chalk)"),
            "T": ("Talkum", "talc")}
FILL_FORM = {"F": ("Fasern", "fibres"), "B": ("Kugeln", "beads"), "D": ("Pulver", "powder")}
FILL = r"(?:-(?P<fm>[GCMKT])(?P<ff>[FBD])(?P<fp>\d{1,2}))?"


def _fill_parts(ctx, m):
    if not m["fm"]:
        return [], ""
    mat, form, pct = FILL_MAT[m["fm"]], FILL_FORM[m["ff"]], m["fp"]
    p = ctx.p(f"{m['fm']}{m['ff']}{pct}", f"Füll-/Verstärkungsstoff nach ISO 1043-2: {mat[0]}{form[0].lower()}, {pct} % (Massenanteil)",
              f"filler/reinforcement per ISO 1043-2: {mat[1]} {form[1]}, {pct} % (by mass)")
    return [p], ctx.t(f"mit {pct} % {mat[0]}{form[0].lower()}", f"with {pct} % {mat[1]} {form[1]}")


def _poly_found(ctx, m, base_code, name, fam_key, parts, extra_txt, refs):
    t = ctx.t
    fp, ftxt = _fill_parts(ctx, m)
    parts += fp
    if fp:
        refs = refs + ["iso-1043-2"]
    fam = ctx.tx(POLY_FAM[fam_key])
    if fp:
        fam = t("verstärkter Kunststoff", "reinforced plastic")
    s = f"{m.group(0)}: {name}" + (f", {extra_txt}" if extra_txt else "") + (f", {ftxt}" if ftxt else "") + f" ({ctx.tx(POLY_FAM[fam_key])})."
    return _found(ctx, m.group(0), "ISO 1043-1" + (" / ISO 1043-2" if fp else ""), fam, parts, s, refs)


def _r_poly(m, ctx):
    t = ctx.t
    base = m["b"]
    unk = []
    if base in POLY_NONISO:
        de, en, fk = POLY_NONISO[base]
        parts = [ctx.p(base, de, en)]
        e = _poly_found(ctx, m, base, t(de.split(" (")[0].split(";")[0], en.split(" (")[0].split(";")[0]), fk, parts, "", ["iso-1043-1"])
        e["system"] = t("gebräuchliches Kurzzeichen", "common abbreviation") + (" / ISO 1043-2" if m["fm"] else "")
        return e
    de, en, fk = POLY[base]
    parts = [ctx.p(base, de, en)]
    extra = ""
    suf = m["s"]
    if suf:
        tab = POLY_SUF.get(base, {})
        if suf in tab:
            parts.append(ctx.p(suf, f"Zusatzzeichen: {ctx.tx(tab[suf])}", f"special characteristic: {ctx.tx(tab[suf])}"))
            extra = ctx.tx(tab[suf])
        else:
            unk.append(f"{suf} (in {m.group(0)})")
    e = _poly_found(ctx, m, base, t(de, en), fk, parts, extra, ["iso-1043-1"])
    if unk:
        e["_unknown"] = unk
    return e


def _r_pa(m, ctx):
    t = ctx.t
    n = m["n"]
    if n not in PA_TYPES:
        return None
    parts = [ctx.p("PA", "Polyamid", "polyamide"),
             ctx.p(n, f"Polyamidtyp {n}: {ctx.tx(PA_TYPES[n])}", f"polyamide type {n}: {ctx.tx(PA_TYPES[n])}")]
    return _poly_found(ctx, m, "PA", t(f"Polyamid {n}", f"polyamide {n}"), "T", parts, "", ["iso-1043-1"])


def _r_uhmwpe(m, ctx):
    t = ctx.t
    parts = [ctx.p(m.group(0), "Polyethylen mit ultrahoher Molmasse; ISO-1043-1-Schreibweise PE-UHMW",
                   "ultra-high molecular weight polyethylene; ISO 1043-1 form PE-UHMW")]
    return _found(ctx, m.group(0), "ISO 1043-1", t("Thermoplast", "thermoplastic"), parts,
                  t(f"{m.group(0)}: Polyethylen mit ultrahoher Molmasse (PE-UHMW).", f"{m.group(0)}: ultra-high molecular weight polyethylene (PE-UHMW)."),
                  ["iso-1043-1"])


# ---------------------------------------------------------------------------- Elastomere (ISO 1629, ISO 18064)
RUBBER_CLASS = {"M": ("Gruppe M: gesättigte Kohlenstoff-Hauptkette", "group M: saturated carbon main chain"),
                "R": ("Gruppe R: ungesättigte Kohlenstoff-Hauptkette", "group R: unsaturated carbon main chain"),
                "Q": ("Gruppe Q: Silicium und Sauerstoff in der Hauptkette (Silikon)", "group Q: silicon and oxygen in the main chain (silicone)"),
                "U": ("Gruppe U: Kohlenstoff, Sauerstoff und Stickstoff in der Hauptkette", "group U: carbon, oxygen and nitrogen in the main chain"),
                "O": ("Gruppe O: Sauerstoff in der Hauptkette", "group O: oxygen in the main chain")}
RUBBER = {
    "NR": ("Naturkautschuk (natürliches Polyisopren)", "natural rubber (natural polyisoprene)", "R", ("N = natürlich", "N = natural")),
    "IR": ("synthetisches Polyisopren", "synthetic polyisoprene", "R", ("I = Isopren", "I = isoprene")),
    "BR": ("Butadienkautschuk", "butadiene rubber", "R", ("B = Butadien", "B = butadiene")),
    "SBR": ("Styrol-Butadien-Kautschuk", "styrene-butadiene rubber", "R", ("S = Styrol, B = Butadien", "S = styrene, B = butadiene")),
    "NBR": ("Acrylnitril-Butadien-Kautschuk (Nitrilkautschuk)", "acrylonitrile-butadiene rubber (nitrile rubber)", "R",
            ("N = Acrylnitril, B = Butadien", "N = acrylonitrile, B = butadiene")),
    "HNBR": ("hydrierter Acrylnitril-Butadien-Kautschuk", "hydrogenated acrylonitrile-butadiene rubber", "R", ("H = hydriert", "H = hydrogenated")),
    "XNBR": ("carboxylierter Acrylnitril-Butadien-Kautschuk", "carboxylated acrylonitrile-butadiene rubber", "R", ("X = carboxyliert", "X = carboxylated")),
    "CR": ("Chloroprenkautschuk", "chloroprene rubber", "R", ("C = Chloropren", "C = chloroprene")),
    "IIR": ("Butylkautschuk (Isobuten-Isopren)", "butyl rubber (isobutene-isoprene)", "R", ("II = Isobuten-Isopren", "II = isobutene-isoprene")),
    "EPDM": ("Ethylen-Propylen-Dien-Kautschuk", "ethylene-propylene-diene rubber", "M",
             ("E = Ethylen, P = Propylen, D = Dien", "E = ethylene, P = propylene, D = diene")),
    "EPM": ("Ethylen-Propylen-Kautschuk", "ethylene-propylene rubber", "M", ("E = Ethylen, P = Propylen", "E = ethylene, P = propylene")),
    "FKM": ("Fluorkautschuk (Substituenten Fluor, Perfluoralkyl- oder Perfluoralkoxygruppen)",
            "fluoro rubber (substituents fluoro, perfluoroalkyl or perfluoroalkoxy groups)", "M", None),
    "FFKM": ("Perfluorkautschuk", "perfluoro rubber", "M", None),
    "ACM": ("Acrylatkautschuk", "acrylic rubber", "M", None),
    "VMQ": ("Silikonkautschuk mit Methyl- und Vinylgruppen", "silicone rubber with methyl and vinyl groups", "Q",
            ("V = Vinyl, M = Methyl", "V = vinyl, M = methyl")),
    "PVMQ": ("Silikonkautschuk mit Phenyl-, Vinyl- und Methylgruppen", "silicone rubber with phenyl, vinyl and methyl groups", "Q",
             ("P = Phenyl, V = Vinyl, M = Methyl", "P = phenyl, V = vinyl, M = methyl")),
    "FVMQ": ("Fluorsilikonkautschuk", "fluorosilicone rubber", "Q", ("F = Fluor(alkyl), V = Vinyl, M = Methyl", "F = fluoro(alkyl), V = vinyl, M = methyl")),
    "MQ": ("Silikonkautschuk mit Methylgruppen", "silicone rubber with methyl groups", "Q", ("M = Methyl", "M = methyl")),
}
TPE = {"A": ("thermoplastisches Polyamid-Elastomer", "thermoplastic polyamide elastomer"),
       "C": ("thermoplastisches Copolyester-Elastomer", "thermoplastic copolyester elastomer"),
       "O": ("thermoplastisches Olefin-Elastomer", "thermoplastic olefinic elastomer"),
       "S": ("thermoplastisches Styrol-Elastomer", "thermoplastic styrenic elastomer"),
       "U": ("thermoplastisches Polyurethan-Elastomer", "thermoplastic polyurethane elastomer"),
       "V": ("thermoplastisches Elastomer mit vernetzter Kautschukphase (Vulkanisat)", "thermoplastic vulcanizate (cross-linked rubber phase)"),
       "Z": ("sonstiges thermoplastisches Elastomer", "other thermoplastic elastomer")}


def _r_rubber(m, ctx):
    t = ctx.t
    code = m.group(0)
    de, en, cl, letters = RUBBER[code]
    parts = [ctx.p(code, de, en)]
    if letters:
        parts.append(ctx.p(code[:-1], *letters))
    parts.append(ctx.p(code[-1], *RUBBER_CLASS[cl]))
    return _found(ctx, code, "ISO 1629", t("Elastomer (Kautschuk)", "elastomer (rubber)"), parts,
                  t(f"{code}: {de}, {RUBBER_CLASS[cl][0]}.", f"{code}: {en}, {RUBBER_CLASS[cl][1]}."), ["iso-1629"])


def _r_tpe(m, ctx):
    t = ctx.t
    k = m["k"]
    parts = [ctx.p("TP", "thermoplastisches Elastomer", "thermoplastic elastomer"), ctx.p(k, *TPE[k])]
    return _found(ctx, m.group(0), "ISO 18064", t("thermoplastisches Elastomer (TPE)", "thermoplastic elastomer (TPE)"), parts,
                  t(f"{m.group(0)}: {TPE[k][0]}.", f"{m.group(0)}: {TPE[k][1]}."), ["iso-18064"])


# ============================================================================ Faserverbunde
COMPOSITE = {"CFK": ("kohlenstofffaserverstärkter Kunststoff", "carbon fibre reinforced plastic (CFRP)"),
             "GFK": ("glasfaserverstärkter Kunststoff", "glass fibre reinforced plastic (GFRP)"),
             "AFK": ("aramidfaserverstärkter Kunststoff", "aramid fibre reinforced plastic (AFRP)"),
             "NFK": ("naturfaserverstärkter Kunststoff", "natural fibre reinforced plastic"),
             "CFRP": ("kohlenstofffaserverstärkter Kunststoff (CFK)", "carbon fibre reinforced plastic"),
             "GFRP": ("glasfaserverstärkter Kunststoff (GFK)", "glass fibre reinforced plastic"),
             "AFRP": ("aramidfaserverstärkter Kunststoff (AFK)", "aramid fibre reinforced plastic")}
UD = ("unidirektional: alle Fasern in einer Richtung", "unidirectional: all fibres in one direction")


def _r_comp(m, ctx):
    t = ctx.t
    k = m["k"]
    parts = [ctx.p(k, *COMPOSITE[k])]
    if m["ud"]:
        parts.append(ctx.p("UD", *UD))
    s = t(f"{m.group(0)}: {COMPOSITE[k][0]}", f"{m.group(0)}: {COMPOSITE[k][1]}") + (t(", unidirektional", ", unidirectional") if m["ud"] else "") + "."
    return _found(ctx, m.group(0), t("Kurzzeichen Faserverbund", "composite abbreviation"), t("Faserverbundwerkstoff", "fibre composite"),
                  parts, s, ["daniel2006"])


FIBRES = {
    "as4": ("PAN-basierte Kohlenstofffaser mit Standardmodul (Handelsname von Hexcel)", "PAN-based standard-modulus carbon fibre (Hexcel trade name)", "C"),
    "im7": ("PAN-basierte Kohlenstofffaser mit Intermediate Modulus (Handelsname von Hexcel)", "PAN-based intermediate-modulus carbon fibre (Hexcel trade name)", "C"),
    "t300": ("Kohlenstofffaser mit Standardmodul (Handelsname von Toray)", "standard-modulus carbon fibre (Toray trade name)", "C"),
    "t700s": ("Kohlenstofffaser mit Standardmodul, hochfest (Handelsname von Toray)", "high-strength standard-modulus carbon fibre (Toray trade name)", "C"),
    "t800s": ("Kohlenstofffaser mit Intermediate Modulus (Handelsname von Toray)", "intermediate-modulus carbon fibre (Toray trade name)", "C"),
    "e-glas": ("E-Glasfaser (E = electrical; alkaliarmes Alumoborosilikatglas, Standard-Glasfaser)",
               "E-glass fibre (E = electrical; low-alkali alumino-borosilicate glass, standard glass fibre)", "G"),
    "e-glass": ("E-Glasfaser (E = electrical; alkaliarmes Alumoborosilikatglas, Standard-Glasfaser)",
                "E-glass fibre (E = electrical; low-alkali alumino-borosilicate glass, standard glass fibre)", "G"),
    "s-glas": ("S-Glasfaser (S = strength, höherfest)", "S-glass fibre (S = strength, higher strength)", "G"),
    "s-glass": ("S-Glasfaser (S = strength, höherfest)", "S-glass fibre (S = strength, higher strength)", "G"),
    "kevlar 49": ("Aramidfaser Kevlar 49 (Handelsname von DuPont; hochmoduliger Typ für Verbunde)",
                  "aramid fibre Kevlar 49 (DuPont trade name; high-modulus type for composites)", "A"),
    "kevlar": ("Aramidfaser (Kevlar: Handelsname von DuPont)", "aramid fibre (Kevlar: DuPont trade name)", "A"),
    "aramid": ("Aramidfaser", "aramid fibre", "A"),
    "carbon": ("Kohlenstofffaser", "carbon fibre", "C"),
    "glass": ("Glasfaser", "glass fibre", "G"),
}
MATRICES = {
    "3501-6": ("Epoxidharzsystem 3501-6 (ursprünglich Hercules, heute Hexcel)", "epoxy resin system 3501-6 (originally Hercules, now Hexcel)"),
    "8552": ("zähmodifiziertes Epoxidharzsystem 8552 (Hexcel)", "toughened epoxy resin system 8552 (Hexcel)"),
    "epoxid": ("Epoxidharz-Matrix", "epoxy matrix"),
    "epoxy": ("Epoxidharz-Matrix", "epoxy matrix"),
}


def _r_fm(m, ctx):
    t = ctx.t
    f, r = m["f"], m["r"]
    fd = FIBRES[f.lower()]
    md = MATRICES[r.lower()]
    parts = [ctx.p(f, *fd[:2]), ctx.p("/", "Faser/Matrix-Schreibweise: vor dem Schrägstrich die Faser, dahinter das Matrixharz",
                                        "fibre/matrix notation: fibre before the slash, matrix resin after it"),
             ctx.p(r, *md)]
    return _found(ctx, m.group(0), t("Faser/Matrix-System", "fibre/matrix system"), t("Faserverbundwerkstoff", "fibre composite"), parts,
                  t(f"{m.group(0)}: Faser/Matrix-System aus {fd[0]} und {md[0]}.", f"{m.group(0)}: fibre/matrix system of {fd[1]} and {md[1]}."),
                  ["daniel2006"])


def _r_cf(m, ctx):
    t = ctx.t
    k = {"SM": ("Standardmodul", "standard modulus"), "IM": ("Intermediate Modulus (mittlerer Modul)", "intermediate modulus"),
         "HM": ("Hochmodul", "high modulus"), "UHM": ("Ultrahochmodul", "ultra-high modulus")}[m["k"]]
    parts = [ctx.p("CF", "Kohlenstofffaser (Carbon Fibre)", "carbon fibre"), ctx.p(m["k"], f"Modulklasse: {k[0]}", f"modulus class: {k[1]}")]
    return _found(ctx, m.group(0), t("gebräuchliches Kurzzeichen", "common abbreviation"), t("Faser", "fibre"), parts,
                  t(f"{m.group(0)}: Kohlenstofffaser, {k[0]}.", f"{m.group(0)}: carbon fibre, {k[1]}."), ["daniel2006"])


# ============================================================================ Klartext, Handelsnamen, Zusätze
PLAIN_EL = {"Al": ("Aluminium", "Aluminum"), "Cu": ("Kupfer", "Copper"), "Fe": ("Eisen", "Iron"), "Ni": ("Nickel",), "Ti": ("Titan", "Titanium"),
            "Mg": ("Magnesium",), "Zn": ("Zink", "Zinc"), "Ag": ("Silber", "Silver"), "Au": ("Gold",), "Pt": ("Platin", "Platinum"),
            "W": ("Wolfram", "Tungsten"), "Mo": ("Molybdän", "Molybdenum"), "Cr": ("Chrom", "Chromium"), "Pb": ("Blei", "Lead"),
            "Sn": ("Zinn", "Tin"), "Co": ("Cobalt", "Kobalt"), "Ta": ("Tantal", "Tantalum"), "Nb": ("Niob", "Niobium"),
            "Si": ("Silicium", "Silizium", "Silicon"), "Ge": ("Germanium",), "C": ()}

# (Art, Wörter, Bedeutung DE, Bedeutung EN, Familie DE, Familie EN, Groß/klein beachten)
VOCAB: list[tuple] = []


def _v(kind, words, de, en, fam_de="", fam_en="", cs=False):
    VOCAB.append((kind, tuple(words), de, en, fam_de, fam_en, cs))


for _sym, _names in PLAIN_EL.items():
    _de, _en = EL[_sym]
    _fam = ("Halbleiter", "semiconductor") if _sym in ("Si", "Ge") else (("Element", "element") if _sym == "C" else ("Reinmetall", "pure metal"))
    _v("plain", _names, f"chemisches Element {_de} ({_sym})", f"chemical element {_en} ({_sym})", *_fam)
    _v("plain", (_sym,), f"Elementsymbol für {_de}", f"element symbol of {_en}", *_fam, cs=True)

_v("plain", ["Aluminiumoxid", "Alumina", "Tonerde"], "Aluminiumoxid Al₂O₃ (Tonerde)", "aluminium oxide Al₂O₃ (alumina)", "Oxidkeramik", "oxide ceramic")
_v("plain", ["Korund"], "Korund: Mineralname des kristallinen α-Al₂O₃", "corundum: mineral name of crystalline α-Al₂O₃", "Oxidkeramik", "oxide ceramic")
_v("plain", ["Siliciumcarbid", "Siliziumkarbid", "Siliziumcarbid", "Silicon carbide"], "Siliciumcarbid SiC", "silicon carbide SiC", "Nichtoxidkeramik", "non-oxide ceramic")
_v("plain", ["Siliciumnitrid", "Siliziumnitrid", "Silicon nitride"], "Siliciumnitrid Si₃N₄", "silicon nitride Si₃N₄", "Nichtoxidkeramik", "non-oxide ceramic")
_v("plain", ["Zirkonoxid", "Zirkonia", "Zirconia"], "Zirconiumdioxid ZrO₂", "zirconium dioxide ZrO₂", "Oxidkeramik", "oxide ceramic")
_v("plain", ["Magnesiumoxid", "Magnesia"], "Magnesiumoxid MgO", "magnesium oxide MgO", "Oxidkeramik", "oxide ceramic")
_v("plain", ["Diamant", "Diamond"], "Diamant: kubische Kohlenstoffmodifikation", "diamond: cubic form of carbon", "Kohlenstoff", "carbon")
_v("plain", ["Quarzglas", "Kieselglas", "Fused silica", "SiO2-Glas"], "Quarzglas: amorphes Siliciumdioxid (SiO₂)", "fused silica: amorphous silicon dioxide (SiO₂)", "Glas", "glass")
_v("plain", ["Kalk-Natron-Glas", "Kalknatronglas", "Soda-lime glass"], "Kalk-Natron-Glas: SiO₂ mit Na₂O und CaO (Flach- und Behälterglas)",
   "soda-lime glass: SiO₂ with Na₂O and CaO (flat and container glass)", "Glas", "glass")
_v("plain", ["Flachglas", "Fensterglas"], "Flach- bzw. Fensterglas (in der Regel Kalk-Natron-Glas)", "flat or window glass (usually soda-lime glass)", "Glas", "glass")
_v("plain", ["Borosilikatglas", "Borosilikat", "Borosilicate glass"], "Borosilikatglas: Glas mit Boroxid, geringe Wärmeausdehnung",
   "borosilicate glass: glass with boron oxide, low thermal expansion", "Glas", "glass")
_v("plain", ["Glaskeramik", "Glass-ceramic"], "Glaskeramik: gezielt teilkristallisiertes Glas", "glass-ceramic: glass with controlled partial crystallization", "Glaskeramik", "glass-ceramic")
_v("plain", ["Beton", "Concrete"], "Beton: Baustoff aus Zement, Gesteinskörnung und Wasser", "concrete: building material of cement, aggregate and water", "Baustoff", "building material")
_v("plain", ["Galliumarsenid", "Gallium arsenide"], "Galliumarsenid GaAs: III-V-Verbindungshalbleiter", "gallium arsenide GaAs: III-V compound semiconductor", "Halbleiter", "semiconductor")
_v("plain", ["Kopierpapier", "Copy paper"], "Kopierpapier (Büropapier)", "copy paper (office paper)", "Papier", "paper")
_v("plain", ["Kraftpapier", "Kraft paper"], "Kraftpapier: Papier aus Sulfatzellstoff mit hoher Festigkeit", "kraft paper: high-strength paper from sulphate pulp", "Papier", "paper")
_v("plain", ["Karton", "Paperboard"], "Karton (Pappe geringer Dicke)", "paperboard", "Papier", "paper")
_v("plain", ["Fichte", "Spruce"], "Fichte (Picea abies), Nadelholz", "spruce (Picea abies), softwood", "Holz", "wood")
_v("plain", ["Buche", "Beech"], "Buche (Fagus sylvatica), Laubholz", "beech (Fagus sylvatica), hardwood", "Holz", "wood")
_v("plain", ["Eiche", "Oak"], "Eiche (Quercus), Laubholz", "oak (Quercus), hardwood", "Holz", "wood")
_v("plain", ["E-Glasfaser", "E-glass fibre", "E-glass fiber", "E-Glas", "E-glass"], "E-Glasfaser (E = electrical; alkaliarmes Alumoborosilikatglas)",
   "E-glass fibre (E = electrical; low-alkali alumino-borosilicate glass)", "Faser", "fibre")
_v("plain", ["Glasfaser", "Glass fibre", "Glass fiber"], "Glasfaser", "glass fibre", "Faser", "fibre")
_v("plain", ["Kohlenstofffaser", "Carbon fibre", "Carbon fiber", "Kohlefaser"], "Kohlenstofffaser (Carbonfaser)", "carbon fibre", "Faser", "fibre")
_v("plain", ["Aramidfaser", "Aramid fibre", "Aramid fiber", "Aramid"], "Aramidfaser (aromatisches Polyamid)", "aramid fibre (aromatic polyamide)", "Faser", "fibre")
_v("plain", ["UHMWPE-Faser"], "Faser aus Polyethylen mit ultrahoher Molmasse", "ultra-high molecular weight polyethylene fibre", "Faser", "fibre")
_v("plain", ["Epoxidharz", "Epoxid", "Epoxy resin", "Epoxy"], "Epoxidharz (Kurzzeichen EP)", "epoxy resin (symbol EP)", "Duroplast", "thermoset")
_v("plain", ["Phenolharz", "Phenol-formaldehyde"], "Phenol-Formaldehyd-Harz (Kurzzeichen PF)", "phenol-formaldehyde resin (symbol PF)", "Duroplast", "thermoset")
_v("plain", ["Naturkautschuk", "Natural rubber"], "Naturkautschuk (Kurzzeichen NR)", "natural rubber (symbol NR)", "Elastomer", "elastomer")
_v("plain", ["Silikonkautschuk", "Silicone rubber", "Silikon", "Silicone"], "Silikonkautschuk (z. B. VMQ)", "silicone rubber (e.g. VMQ)", "Elastomer", "elastomer")
_v("plain", ["Al2O3"], "chemische Formel von Aluminiumoxid", "chemical formula of aluminium oxide", "Oxidkeramik", "oxide ceramic", cs=True)
_v("plain", ["SiC"], "chemische Formel von Siliciumcarbid", "chemical formula of silicon carbide", "Nichtoxidkeramik", "non-oxide ceramic", cs=True)
_v("plain", ["Si3N4"], "chemische Formel von Siliciumnitrid", "chemical formula of silicon nitride", "Nichtoxidkeramik", "non-oxide ceramic", cs=True)
_v("plain", ["ZrO2"], "chemische Formel von Zirconiumdioxid", "chemical formula of zirconium dioxide", "Oxidkeramik", "oxide ceramic", cs=True)
_v("plain", ["MgO"], "chemische Formel von Magnesiumoxid", "chemical formula of magnesium oxide", "Oxidkeramik", "oxide ceramic", cs=True)
_v("plain", ["GaAs"], "chemische Formel von Galliumarsenid", "chemical formula of gallium arsenide", "Halbleiter", "semiconductor", cs=True)
_v("plain", ["3Y-TZP"], "3Y-TZP: mit 3 mol% Y₂O₃ stabilisiertes tetragonales Zirconiumdioxid-Polykristall",
   "3Y-TZP: tetragonal zirconia polycrystal stabilized with 3 mol% Y₂O₃", "Oxidkeramik", "oxide ceramic", cs=True)

_v("trade", ["Pyrex"], "Pyrex: Handelsname (ursprünglich Corning) für Borosilikatglas", "Pyrex: trade name (originally Corning) for borosilicate glass", "Glas", "glass")
_v("trade", ["Duran"], "Duran: Handelsname (ursprünglich Schott) für Borosilikatglas", "Duran: trade name (originally Schott) for borosilicate glass", "Glas", "glass")
_v("trade", ["Pyroceram"], "Pyroceram: Handelsname (Corning) für Glaskeramik", "Pyroceram: trade name (Corning) for glass-ceramic", "Glaskeramik", "glass-ceramic")
_v("trade", ["Kevlar 49"], "Kevlar 49: Handelsname (DuPont) einer hochmoduligen Aramidfaser", "Kevlar 49: trade name (DuPont) of a high-modulus aramid fibre", "Faser", "fibre")
_v("trade", ["Spectra 900"], "Spectra 900: Handelsname (Honeywell) einer UHMW-PE-Faser", "Spectra 900: trade name (Honeywell) of a UHMW-PE fibre", "Faser", "fibre")
_v("trade", ["Dyneema"], "Dyneema: Handelsname (ursprünglich DSM) einer UHMW-PE-Faser", "Dyneema: trade name (originally DSM) of a UHMW-PE fibre", "Faser", "fibre")
_v("trade", ["Kapton HN"], "Kapton HN: Handelsname (DuPont) einer Polyimidfolie, Typ HN (Standardtyp)",
   "Kapton HN: trade name (DuPont) of a polyimide film, type HN (general purpose)", "Folie", "film")
_v("trade", ["Kapton"], "Kapton: Handelsname (DuPont) für Polyimidfolie", "Kapton: trade name (DuPont) for polyimide film", "Folie", "film")
_v("trade", ["Bakelit", "Bakelite"], "Bakelit: historischer Handelsname für Phenol-Formaldehyd-Harz", "Bakelite: historic trade name for phenol-formaldehyde resin",
   "Duroplast", "thermoset")
_v("trade", ["V2A"], "V2A: historischer Krupp-Markenname (1912) für austenitischen Chrom-Nickel-Stahl, heute umgangssprachlich für 1.4301",
   "V2A: historic Krupp brand name (1912) for austenitic chromium-nickel steel, colloquially used for 1.4301", "nichtrostender Stahl", "stainless steel", cs=True)
_v("trade", ["V4A"], "V4A: historischer Krupp-Markenname für molybdänhaltigen Chrom-Nickel-Stahl, heute umgangssprachlich für 1.4401/1.4404/1.4571",
   "V4A: historic Krupp brand name for molybdenum-bearing chromium-nickel steel, colloquially used for 1.4401/1.4404/1.4571",
   "nichtrostender Stahl", "stainless steel", cs=True)
_v("trade", ["Plexiglas"], "Plexiglas: Handelsname für PMMA", "Plexiglas: trade name for PMMA", "Thermoplast", "thermoplastic")

_v("qual", ["weich", "annealed", "soft"], "weich (geglüht): rekristallisiert, niedrigste Festigkeit und höchste Dehnung der Sorte",
   "annealed (soft): recrystallized, lowest strength and highest elongation of the grade")
_v("qual", ["halbhart", "half hard", "half-hard"], "halbhart: mittlere Kaltverfestigung", "half hard: medium degree of cold work")
_v("qual", ["hart", "hard"], "hart: stark kaltverfestigt (hohe Festigkeit, geringe Dehnung)", "hard: heavily cold worked (high strength, low elongation)")
_v("qual", ["trocken", "dry", "dry as moulded"], "trocken (spritzfrisch): ohne aufgenommene Feuchte geprüft; Polyamide nehmen danach Wasser auf und werden weicher und zäher",
   "dry as moulded: tested without absorbed moisture; polyamides later absorb water and become softer and tougher")
_v("qual", ["konditioniert", "conditioned"], "konditioniert: bis zum Feuchtegleichgewicht im Normklima 23 °C / 50 % r. F. gelagert (ISO 291, beschleunigt nach ISO 1110)",
   "conditioned: stored to moisture equilibrium at 23 °C / 50 % RH (ISO 291, accelerated per ISO 1110)")
_v("qual", ["längs", "machine direction"], "längs: in Maschinenrichtung (Laufrichtung der Bahn bei der Herstellung) geprüft",
   "machine direction (MD): tested along the running direction of the web during manufacture")
_v("qual", ["MD"], "MD (machine direction): in Maschinenrichtung geprüft", "MD: machine direction", cs=True)
_v("qual", ["quer", "transverse"], "quer: senkrecht zur Maschinenrichtung geprüft", "transverse direction (TD): tested across the machine direction")
_v("qual", ["TD"], "TD (transverse direction): quer zur Maschinenrichtung", "TD: transverse direction", cs=True)
_v("qual", ["Folie", "film"], "Folie (dünnes Flachprodukt)", "film (thin flat product)")
_v("qual", ["Blasfolie", "blown"], "Blasfolie: im Folienblasverfahren hergestellt", "blown film: produced by film blowing")
_v("qual", ["BOPET"], "BOPET: biaxial orientierte PET-Folie (in Längs- und Querrichtung verstreckt)", "BOPET: biaxially oriented PET film (stretched in both directions)", cs=True)
_v("qual", ["BOPP"], "BOPP: biaxial orientierte PP-Folie (in Längs- und Querrichtung verstreckt)", "BOPP: biaxially oriented PP film (stretched in both directions)", cs=True)
_v("qual", ["vergütet", "quenched and tempered"], "vergütet: gehärtet und angelassen", "quenched and tempered")
_v("qual", ["geglüht"], "geglüht (weichgeglüht)", "annealed")
_v("qual", ["normalgeglüht", "normalized", "normalised"], "normalgeglüht", "normalized")
_v("qual", ["warmgewalzt", "hot rolled", "hot-rolled"], "warmgewalzt (Walzzustand)", "hot rolled (as rolled)")
_v("qual", ["kaltgewalzt", "cold rolled", "cold-rolled"], "kaltgewalzt", "cold rolled")
_v("qual", ["ausgehärtet", "aged"], "ausgehärtet: lösungsgeglüht und durch Auslagern ausscheidungsgehärtet", "aged: solution treated and precipitation hardened by ageing")
_v("qual", ["rein", "pure"], "rein: unlegiert, hohe Reinheit", "pure: unalloyed, high purity")
_v("qual", ["α-Fe"], "α-Fe: kubisch-raumzentrierte Modifikation des Eisens (Ferrit, stabil bis 911 °C)",
   "α-Fe: body-centred cubic form of iron (ferrite, stable up to 911 °C)", cs=True)
_v("qual", ["β-Sn"], "β-Sn: weißes, tetragonales Zinn (stabil oberhalb 13,2 °C)", "β-Sn: white, tetragonal tin (stable above 13.2 °C)", cs=True)
_v("qual", ["α-Ti"], "α-Ti: hexagonale Modifikation des Titans (stabil bis 882 °C)", "α-Ti: hexagonal form of titanium (stable up to 882 °C)", cs=True)
_v("qual", ["einkristallin", "single crystal", "single-crystal"], "einkristallin: ein einziger Kristall ohne Korngrenzen", "single crystal: one crystal without grain boundaries")
_v("qual", ["gesintert", "sintered"], "gesintert: aus Pulver durch Sintern verdichtet", "sintered: densified from powder by sintering")
_v("qual", ["heißgepresst", "hot pressed", "hot-pressed"], "heißgepresst: unter Druck gesintert", "hot pressed: sintered under pressure")
_v("qual", ["synthetisch", "synthetic"], "synthetisch hergestellt", "synthetically produced")
_v("plain", ["Periklas", "periclase"], "Periklas: Mineralname von Magnesiumoxid (MgO)", "periclase: mineral name of magnesium oxide (MgO)",
   "Oxidkeramik", "oxide ceramic")
_v("qual", ["ähnlich", "similar"], "ähnlich: vergleichbare, nicht identische Sorte", "similar: comparable, not identical grade")
_v("qual", ["Copolymer"], "Copolymer: aus zwei oder mehr Monomeren aufgebaut", "copolymer: built from two or more monomers")
_v("qual", ["Homopolymer"], "Homopolymer: aus einem Monomer aufgebaut", "homopolymer: built from one monomer")
_v("qual", ["Standard", "general purpose"], "Standardtyp (ohne Modifizierung)", "general purpose type (unmodified)")
_v("qual", ["ungefüllt", "unfilled"], "ungefüllt: ohne Füll- und Verstärkungsstoffe", "unfilled: without fillers or reinforcements")
_v("qual", ["Messing", "brass"], "Messing: Kupfer-Zink-Legierung", "brass: copper-zinc alloy")
_v("qual", ["Bronze"], "Bronze: Kupferlegierung, deren Hauptlegierungselement nicht Zink ist (meist Zinn)",
   "bronze: copper alloy whose main alloying element is not zinc (usually tin)")
_v("qual", ["unidirektional", "unidirectional"], *UD)
_v("qual", ["UD"], *UD, cs=True)
_v("qual", ["Gewebe", "woven fabric", "woven"], "Gewebe: Fasern in zwei Richtungen verwoben", "woven fabric: fibres interlaced in two directions")
_v("qual", ["Zug parallel zur Faser", "tension parallel to grain"], "Zugbeanspruchung parallel zur Faser (Holz: in Stammrichtung)",
   "tension parallel to the grain (wood: along the stem)")
_v("qual", ["Faser", "fibre", "fiber"], "Faser", "fibre")
_v("qual", ["Standardmodul", "standard modulus"], "Standardmodul (Kohlenstofffaser)", "standard modulus (carbon fibre)")
_v("qual", ["Intermediate Modulus", "mittlerer Modul"], "Intermediate Modulus: mittlerer Modul (Kohlenstofffaser)", "intermediate modulus (carbon fibre)")
_v("qual", ["Hochmodul", "high modulus"], "Hochmodul (Kohlenstofffaser)", "high modulus (carbon fibre)")
_v("qual", ["SM"], "SM: Standardmodul", "SM: standard modulus", cs=True)
_v("qual", ["IM"], "IM: Intermediate Modulus", "IM: intermediate modulus", cs=True)
_v("qual", ["HM"], "HM: Hochmodul", "HM: high modulus", cs=True)
_v("qual", ["PAN"], "PAN: aus Polyacrylnitril-Precursorfasern hergestellt", "PAN: made from polyacrylonitrile precursor fibres", cs=True)
_v("qual", ["Kohlenstoff"], "Kohlenstoff", "carbon")


QUAL_REFS = {"konditioniert": ["iso-291", "iso-1110"], "BOPET": ["iso-1043-1"], "BOPP": ["iso-1043-1"]}


def _vocab_regex(cs: bool):
    words = sorted({w for e in VOCAB if e[6] == cs for w in e[1]}, key=len, reverse=True)
    alt = "|".join(re.escape(w).replace(r"\ ", r"\s+") for w in words)
    return re.compile(rf"(?:{alt})" + _END, 0 if cs else re.IGNORECASE)


_END = r"(?=$|[\s,;()\[\]/+:\-]|\.(?:\s|$))"


def _vocab_lookup(text: str, cs: bool):
    key = re.sub(r"\s+", " ", text)
    for e in VOCAB:
        if e[6] != cs:
            continue
        for w in e[1]:
            if (w == key) if cs else (w.casefold() == key.casefold()):
                return e
    return None


def _vocab_handler(cs):
    def h(m, ctx):
        e = _vocab_lookup(m.group(0), cs)
        if not e:
            return None
        kind, _, de, en, fde, fen, _ = e
        code = re.sub(r"\s+", " ", m.group(0))
        if kind == "qual":
            return _qual(code, ctx.t(de, en), QUAL_REFS.get(e[1][0]))
        if kind == "trade":
            return _found(ctx, code, ctx.t("Handelsname", "trade name"), ctx.t(fde, fen), [ctx.p(code, de, en)],
                          ctx.t(f"{code}: {de}.", f"{code}: {en}."), [], plain=True)
        return _found(ctx, code, ctx.t("Klartext (keine Normbezeichnung)", "plain name (no standard designation)"), ctx.t(fde, fen),
                      [ctx.p(code, de, en)], ctx.t(f"{code}: Klartextname ohne Normbezeichnung – {de}.",
                                                   f"{code}: plain name, no standard designation – {en}."), [], plain=True)
    return h


def _q_temper_c(m, ctx):
    return _qual(re.sub(r"\s+", " ", m.group(0)), ctx.t(f"angelassen bei {m['v']} °C", f"tempered at {m['v']} °C"))


def _q_qt(m, ctx):
    return _qual(m.group(0), ctx.t(f"vergütet, angelassen bei {m['v']} °C (Kurzschreibweise der Datenbank, keine Normbezeichnung)",
                                   f"quenched and tempered at {m['v']} °C (database short form, not a standard designation)"))


def _q_qt_en(m, ctx):
    return _qual(re.sub(r"\s+", " ", m.group(0)), ctx.t(f"vergütet (gehärtet und angelassen), Anlasstemperatur {m['v']} °C",
                                                        f"quenched and tempered, tempering temperature {m['v']} °C"))


def _q_gsm(m, ctx):
    return _qual(m.group(0), ctx.t(f"flächenbezogene Masse (Grammatur) {m['v']} g/m²", f"grammage (mass per unit area) {m['v']} g/m²"))


def _q_um(m, ctx):
    return _qual(m.group(0), ctx.t(f"Dicke {ctx.num(m['v'])} µm", f"thickness {ctx.num(m['v'])} µm"))


def _q_mol(m, ctx):
    return _qual(re.sub(r"\s+", " ", m.group(0)), ctx.t(f"stabilisiert mit {ctx.num(m['v'])} mol% Yttriumoxid (Y₂O₃)",
                                                        f"stabilized with {ctx.num(m['v'])} mol% yttria (Y₂O₃)"))


def _q_pct(m, ctx):
    return _qual(m.group(0), ctx.t(f"Gehaltsangabe {ctx.num(m['v'])} % (Reinheit bzw. Anteil der Hauptkomponente)",
                                   f"content {ctx.num(m['v'])} % (purity or fraction of the main component)"))


def _q_shore(m, ctx):
    sc = m["s"]
    rng = ctx.t("weiche Kunststoffe und Elastomere", "soft plastics and elastomers") if sc == "A" else ctx.t("härtere Kunststoffe", "harder plastics")
    return _qual(re.sub(r"\s+", " ", m.group(0)), ctx.t(f"Shore-Härte {m['v']} auf der Skala {sc} (0–100, ISO 868; Skala {sc} für {rng})",
                                                        f"Shore hardness {m['v']} on scale {sc} (0–100, ISO 868; scale {sc} for {rng})"),
                 ["iso-868"])


def _q_angle(m, ctx):
    return _qual(m.group(0), ctx.t(f"Belastung unter {m['v']}° zur Faserrichtung", f"loaded at {m['v']}° to the fibre direction"))


def _q_treat(m, ctx):
    sym = m["s"]
    if sym not in TREAT:
        return None
    return _qual(m.group(0), ctx.t(f"Behandlungszustand nach EN 10027-1: {TREAT[sym][0]}", f"treatment condition per EN 10027-1: {TREAT[sym][1]}"),
                 ["en-10027-1"])


# ============================================================================ Regeln
def _rx(p, flags=0):
    return re.compile(p + _END, flags)


_RULES = [
    (_rx(rf"(?P<en>EN[\s-]?)?AW[\s-]?(?P<num>\d{{4}})(?P<var>[A-Z])?(?:[\s-](?P<temp>{TEMPS_AL}))?"), _r_al_num),
    (_rx(r"EN[\s-]?AC[\s-]?(?P<num>\d{5})"), _r_al_ac),
    (_rx(rf"(?P<en>EN[\s-]?AW[\s-]?)?Al ?(?P<body>99(?:[,.]\d{{1,2}})?(?:(?:{AL_EL})(?:\d+(?:[,.]\d+)?)?)*|(?:(?:{AL_EL})(?:\d+(?:[,.]\d+)?)?)+)"
         rf"(?P<var>\([A-Z]\))?(?:[\s-](?P<temp>{TEMPS_AL}))?"), _r_al_chem),
    (_rx(rf"(?P<num>\d{{4}})(?P<var>[A-Z])?-(?P<temp>{TEMPS_AL})"), _r_al_bare),
    (_rx(r"(?P<g>G)?(?P<l>[SPLE])(?P<v>\d{3})(?P<suf>[A-Z][A-Z0-9]*)?" + TR), _r_steel_g1),
    (_rx(r"D(?P<k>[CDX])(?P<n>\d{2})(?P<suf>D|EK|ED)?" + TR), _r_steel_d),
    (_rx(r"H(?P<k>[CDX])(?P<n>\d{3})(?P<suf>LA|[BIPY])?"), _r_steel_h),
    (_rx(r"B(?P<v>\d{3})(?P<c>[ABC])?"), _r_steel_b),
    (_rx(r"Y(?P<v>\d{4})(?P<c>[CHQS])"), _r_steel_y),
    (_rx(r"R(?P<v>\d{3})(?P<s>LHT|HT|Cr|Mn)?"), _r_steel_r),
    (_rx(r"M(?P<v>\d{3,4})-(?P<d>\d{2,3})(?P<k>[A-Z])"), _r_steel_m),
    (_rx(r"(?P<g>G)?C(?P<c>\d{1,3})(?P<suf>[CDERSUWG]{0,2})" + TR), _r_steel_c),
    (_rx(r"(?P<g>G)?(?P<c>\d{1,3})(?P<el>(?:[A-Z][a-z]?)+)(?P<n>\d{1,4}(?:-\d{1,4})*)" + TR), _r_steel_low),
    (_rx(r"(?P<g>G)?X(?P<c>\d{1,3})(?P<el>(?:[A-Z][a-z]?)+)(?P<n>\d+(?:[,.]\d+)?(?:-\d+(?:[,.]\d+)?)*)" + TR), _r_steel_x),
    (_rx(r"HS(?P<n>\d+(?:[,.]\d+)?(?:-\d+(?:[,.]\d+)?){2,3})" + TR), _r_steel_hs),
    (_rx(r"1\.(?P<g>\d{2})(?P<y>\d{2})(?P<z>\d{2})?" + TR), _r_steel_num),
    (_rx(r"St\s?(?P<n>\d{2})(?:-(?P<q>\d))?"), _r_old_st),
    (_rx(r"Ck\s?(?P<c>\d{2,3})" + TR), _r_old_ck),
    (_rx(r"(?P<k>GGG|GG)-?\s?(?P<n>\d{2})"), _r_old_gg),
    (_rx(r"(?P<org>AISI|SAE)\s?(?P<num>\d{4,5})(?P<h>H)?" + TR), _r_sae),
    (_rx(r"(?:(?P<org>AISI|SAE)\s?)?(?P<num>\d{3})(?P<suf>LN|Ti|L|H|N)?"), _r_aisi_ss),
    (_rx(r"(?P<num>\d{4})" + TR), _r_bare4),
    (_rx(r"(?P<en>EN[\s-]?)?GJ(?P<gr>[LSMVNY])(?P<mi>[AFPMLQTBW])?(?:-(?P<rm>\d{2,4})|-HB(?P<hb>\d{3}))?(?:-(?P<a>\d{1,2}))?(?:-(?P<t>LT|RT))?"), _r_gj),
    (_rx(r"Cu-(?P<ty>FRHC|ETP|OFE|OF|DHP|DLP|PHC|HCP)" + COND), _r_cu_type),
    (_rx(r"Cu(?P<body>(?:(?:" + "|".join(sorted(CU_EL, key=len, reverse=True)) + r")(?:\d+(?:[,.]\d+)?)?)+)" + COND), _r_cu_chem),
    (_rx(r"C(?P<f>[WBCFMRSX])(?P<n>\d{3})(?P<g>[A-HJ-NPRS])" + COND), _r_cu_num),
    (_rx(r"Ms\s?(?P<n>\d{2})"), _r_ms),
    (_rx(r"(?:(?P<ti>Titan|Titanium|Ti)\s?)?Grade\s?(?P<g>\d{1,2})(?:\s?(?P<eli>ELI))?"), _r_ti_grade),
    (_rx(r"Ti-(?P<body>\d+(?:[.,]\d+)?[A-Z][a-z]?(?:-\d+(?:[.,]\d+)?[A-Z][a-z]?)*)(?:\s?(?P<eli>ELI))?"), _r_ti_alloy),
    (_rx(r"Ti64"), _r_ti64),
    (_rx(rf"(?P<a>[A-Z])(?P<b>[A-Z])(?P<x>\d)(?P<y>\d)(?P<s>[A-EX])?(?:-(?P<temp>{TEMP_MG}))?"), _r_mg),
    (_rx(r"(?P<b>Nickel|Inconel|Incoloy|Monel|Hastelloy|Alloy)\s?(?P<n>C-276|\d{3})"), _r_ni),
    (_rx(r"Ni\s?(?P<p>99[,.]\d{1,2})"), _r_ni_pure),
    (_rx(r"Ni(?P<body>(?:(?:Cr|Mo|Fe|Cu|Co|Nb|Ti|Al|W|Mn|Si|Ta)(?:\d+(?:[,.]\d+)?)?)+)"), _r_ni_chem),
    (_rx(r"UNS\s?(?P<l>[A-Z])(?P<n>\d{5})"), _r_uns),
    (_rx(rf"(?P<h>[23])\.(?P<s>\d)(?P<r>\d{{3}})(?:\s(?P<temp>{TEMPS_AL}))?"), _r_din_nf),
    (_rx(r"PA\s?(?P<n>1010|610|612|11|12|46|66|6)" + FILL), _r_pa),
    (_rx(r"(?P<b>" + "|".join(sorted(list(POLY) + list(POLY_NONISO), key=len, reverse=True)) + r")(?:-(?P<s>UHMW|HMW|LLD|HD|LD|MD|[HBRUPCX]))?" + FILL), _r_poly),
    (_rx(r"UHMW-?PE"), _r_uhmwpe),
    (_rx(r"(?:" + "|".join(sorted(RUBBER, key=len, reverse=True)) + r")"), _r_rubber),
    (_rx(r"TP(?P<k>[ACOSUVZ])"), _r_tpe),
    (_rx(r"(?P<k>CFRP|GFRP|AFRP|CFK|GFK|AFK|NFK)(?:-(?P<ud>UD))?"), _r_comp),
    (_rx(r"(?P<f>" + "|".join(re.escape(k).replace(r"\ ", r"\s") for k in sorted(FIBRES, key=len, reverse=True)) + r")/(?P<r>"
         + "|".join(re.escape(k) for k in sorted(MATRICES, key=len, reverse=True)) + r")", re.IGNORECASE), _r_fm),
    (_rx(r"CF-(?P<k>UHM|SM|IM|HM)"), _r_cf),
    (_rx(r"Anlassen\s+(?P<v>\d{2,4})\s?°C"), _q_temper_c),
    (_rx(r"quenched and tempered at\s+(?P<v>\d{2,4})\s?°C", re.IGNORECASE), _q_qt_en),
    (_rx(r"tempered at\s+(?P<v>\d{2,4})\s?°C", re.IGNORECASE), _q_temper_c),
    (_rx(r"QT(?P<v>\d{3})"), _q_qt),
    (_rx(r"(?P<v>\d{2,4})\s?g/m[²2]"), _q_gsm),
    (_rx(r"(?P<v>\d+(?:[,.]\d+)?)\s?[µμ]m"), _q_um),
    (_rx(r"(?P<v>\d+(?:[,.]\d+)?)\s?mol\s?%\s?Y2O3"), _q_mol),
    (_rx(r"(?P<v>\d+(?:[,.]\d+)?)\s?%"), _q_pct),
    (_rx(r"(?P<v>\d{1,3})\s?Shore\s?(?P<s>[AD])"), _q_shore),
    (_rx(r"(?P<v>\d{1,3})\s?°(?!\s?C)"), _q_angle),
    (_rx(r"\+(?P<s>[A-Z]{1,3})"), _q_treat),
]
_RULES.append((_vocab_regex(True), _vocab_handler(True)))
_RULES.append((_vocab_regex(False), _vocab_handler(False)))

_SKIP = set(" \t\r\n,;()[]/-:·")
_WORD_END = set(" \t\r\n,;()[]")


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFC", s)
    for a, b in ((" ", " "), (" ", " "), (" ", " "), ("‑", "-"), ("‐", "-")):
        s = s.replace(a, b)
    return s


_HINTS = {"aluminium": "al", "aluminum": "al", "stahl": "steel", "edelstahl": "steel", "steel": "steel", "stainless steel": "steel",
          "magnesium": "mg", "kupfer": "cu", "copper": "cu", "titan": "ti", "titanium": "ti", "nickel": "ni", "gusseisen": "fe", "cast iron": "fe"}


def _hint_key(hint):
    if not hint:
        return None
    h = str(hint).strip().casefold()
    return _HINTS.get(h, h)


def _summary(ctx, found, quals, unknown, notes) -> str:
    t = ctx.t
    bits = []
    if not found and not quals and not unknown:
        return t("Keine Bezeichnung angegeben.", "No designation given.")
    if found:
        bits += [f["summary"] for f in found]
    else:
        bits.append(t("Keine genormte Bezeichnung erkannt.", "No standard designation recognized."))
    if quals:
        def _q(q):
            same = q["meaning"].casefold().startswith(q["code"].casefold())
            return q["meaning"] if same else f"{q['code']} = {q['meaning']}"
        bits.append(t("Zusätze: ", "Qualifiers: ") + "; ".join(_q(q) for q in quals) + ".")
    bits += notes
    if unknown:
        bits.append(t("Nicht erklärt (keine Regel): ", "Not explained (no rule): ") + ", ".join(f"„{u}“" if ctx.lang == "de" else f"“{u}”"
                                                                                           for u in unknown) + ".")
    return " ".join(bits)


def decode(text: str, lang: str = "de", hint: str | None = None) -> dict:
    """Bezeichnung(en) in ``text`` zerlegen und erklären.

    Rückgabe: ``{"input", "found": [{code, system, family, parts, summary, composition?, refs}], "qualifiers": [{code, meaning}],
    "unknown": [...], "notes": [...], "summary"}``. ``hint`` (z. B. die Werkstofffamilie „Stahl“ oder „Aluminium“) löst
    mehrdeutige Kurzformen wie eine nackte vierstellige Zahl auf.
    """
    lang = "en" if str(lang or "de").lower().startswith("en") else "de"
    src = "" if text is None else str(text)
    s = _norm(src)
    ctx = _Ctx(lang, _hint_key(hint))
    found, quals, unknown, notes = [], [], [], []
    i, n = 0, len(s)
    while i < n:
        if s[i] in _SKIP:
            i += 1
            continue
        cands = []
        for prio, (rx, fn) in enumerate(_RULES):
            m = rx.match(s, i)
            if m and m.end() > i:
                cands.append((-(m.end()), prio, m, fn))
        cands.sort(key=lambda c: (c[0], c[1]))
        done = False
        for _, _, m, fn in cands:
            r = fn(m, ctx)
            if r is None:
                continue
            kind = r.pop("_kind")
            if kind == "found":
                unknown += r.pop("_unknown", [])
                found.append(r)
            elif kind == "qual":
                quals.append(r)
            else:
                unknown.append(r["text"])
                notes.append(r["note"])
            i = m.end()
            done = True
            break
        if done:
            continue
        j = i
        while j < n and s[j] not in _WORD_END:
            j += 1
        unknown.append(s[i:j])
        i = j
    return {"input": src, "found": found, "qualifiers": quals, "unknown": unknown, "notes": notes,
            "summary": _summary(ctx, found, quals, unknown, notes)}


def _ckey(code: str) -> str:
    return re.sub(r"[\s\-_.,/()]+", "", code).casefold()


def decode_material(name_or_id, lang: str = "de") -> dict:
    """Name und Aliase eines Werkstoffs der Datenbank (``materials.find``) erklären.

    ``found``/``unknown`` enthalten die Treffer aus dem Namen und – ohne Doppelungen, mit ``"from": Alias`` markiert – aus den
    Aliasen; ``aliases`` listet die Einzelergebnisse je Alias. Die Werkstofffamilie dient als ``hint``.
    """
    from . import materials as M
    r = M.find(name_or_id)
    lang = "en" if str(lang or "de").lower().startswith("en") else "de"
    name = (r.get("name_en") or r["name"]) if lang == "en" else r["name"]
    hint = r.get("familie")
    res = decode(name, lang, hint=hint)
    res["material"] = {"id": r.get("id"), "name": r.get("name"), "name_en": r.get("name_en"), "klasse": r.get("klasse"),
                       "familie": r.get("familie")}
    seen = {_ckey(f["code"]) for f in res["found"]}
    aliases = []
    more = []
    for a in r.get("aliase") or []:
        d = decode(a, lang, hint=hint)
        aliases.append(d)
        for f in d["found"]:
            k = _ckey(f["code"])
            if k not in seen:
                seen.add(k)
                res["found"].append({**f, "from": a})
                more.append(f["code"])
        for u in d["unknown"]:
            if u not in res["unknown"]:
                res["unknown"].append(u)
        for nt in d["notes"]:
            if nt not in res["notes"]:
                res["notes"].append(nt)
    res["aliases"] = aliases
    if more:
        res["summary"] += (" Weitere Bezeichnungen: " if lang == "de" else " Other designations: ") + ", ".join(more) + "."
    alias_unknown = [u for d in aliases for u in d["unknown"]]
    if alias_unknown:
        res["summary"] += (" In den Aliasen nicht erklärt: " if lang == "de" else " Not explained in the aliases: ") + ", ".join(alias_unknown) + "."
    return res
