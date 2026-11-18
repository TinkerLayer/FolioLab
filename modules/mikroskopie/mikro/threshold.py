"""Automatische Schwellenwerte auf einem 256-Klassen-Histogramm.

Jede Methode liefert den Index k (0..255) der letzten Klasse des *unteren* Teils: Objekte auf dunklem
Hintergrund sind dann alle Klassen > k, Objekte auf hellem Hintergrund alle Klassen <= k.
Fuer 16- und 32-bit-Bilder werden die 256 Klassen gleichmaessig zwischen Minimum und Maximum gelegt.
"""
from __future__ import annotations

import math

import numpy as np

# Schluessel -> (Anzeigename, Literaturschluessel)
METHODS = {
    "default": ("Default (IsoData-Variante)", "ridler1978"),
    "isodata": ("IsoData", "ridler1978"),
    "otsu": ("Otsu", "otsu1979"),
    "triangle": ("Dreieck (Triangle)", "zack1977"),
    "li": ("Li", "li1993"),
    "huang": ("Huang", "huang1995"),
    "maxentropy": ("Maximale Entropie", "kapur1985"),
    "yen": ("Yen", "yen1995"),
    "moments": ("Momente", "tsai1985"),
    "mean": ("Mittelwert", "glasbey1993"),
    "minimum": ("Minimum", "prewitt1966"),
    "intermodes": ("Intermodes", "prewitt1966"),
    "percentile": ("Perzentil (50 %)", "doyle1962"),
}

# MI-02 (17.11.2026): Angaben mit DOI gegen Crossref geprüft (Autoren, Jahr, Band, Heft, Seiten).
# tsai1985 und prewitt1966 (SF, 18.11.2026): Verfahren mit der Beschreibung abgeglichen (Tsai: erste drei Momente
# erhalten, Schwelle beim p0-Quantil; Prewitt & Mendelsohn: 3-Punkt-Glättung bis zu genau zwei Maxima, Mitte der
# Maxima bzw. Tal dazwischen, wie bei Glasbey 1993 beschrieben); Autoren, Titel, Zeitschrift, Band, Seiten und Jahr
# bestätigt. Ohne DOI und ohne Heftnummer, weil diese offline nicht geprüft werden konnten.
# Schlüssel, die hier stehen, bekommen im Bericht den Vermerk „nicht verifiziert“.
UNVERIFIED: set = set()

REFERENCES = {
    "ridler1978": dict(entry_type="article", author="Ridler, T. W. and Calvard, S.",
                       title="Picture thresholding using an iterative selection method",
                       journal="IEEE Transactions on Systems, Man, and Cybernetics", volume="8", number="8",
                       pages="630--632", year="1978", doi="10.1109/TSMC.1978.4310039"),
    "otsu1979": dict(entry_type="article", author="Otsu, Nobuyuki",
                     title="A threshold selection method from gray-level histograms",
                     journal="IEEE Transactions on Systems, Man, and Cybernetics", volume="9", number="1",
                     pages="62--66", year="1979", doi="10.1109/TSMC.1979.4310076"),
    "zack1977": dict(entry_type="article", author="Zack, G. W. and Rogers, W. E. and Latt, S. A.",
                     title="Automatic measurement of sister chromatid exchange frequency",
                     journal="Journal of Histochemistry and Cytochemistry", volume="25", number="7",
                     pages="741--753", year="1977", doi="10.1177/25.7.70454"),
    "li1993": dict(entry_type="article", author="Li, C. H. and Lee, C. K.", title="Minimum cross entropy thresholding",
                   journal="Pattern Recognition", volume="26", number="4", pages="617--625", year="1993", doi="10.1016/0031-3203(93)90115-D"),
    "huang1995": dict(entry_type="article", author="Huang, Liang-Kai and Wang, Mao-Jiun J.",
                      title="Image thresholding by minimizing the measures of fuzziness", journal="Pattern Recognition",
                      volume="28", number="1", pages="41--51", year="1995", doi="10.1016/0031-3203(94)E0043-K"),
    "kapur1985": dict(entry_type="article", author="Kapur, J. N. and Sahoo, P. K. and Wong, A. K. C.",
                      title="A new method for gray-level picture thresholding using the entropy of the histogram",
                      journal="Computer Vision, Graphics, and Image Processing", volume="29", number="3",
                      pages="273--285", year="1985", doi="10.1016/0734-189X(85)90125-2"),
    "yen1995": dict(entry_type="article", author="Yen, Jui-Cheng and Chang, Fu-Juay and Chang, Shyang",
                    title="A new criterion for automatic multilevel thresholding",
                    journal="IEEE Transactions on Image Processing", volume="4", number="3", pages="370--378", doi="10.1109/83.366472",
                    year="1995"),
    "tsai1985": dict(entry_type="article", author="Tsai, Wen-Hsiang",
                     title="Moment-preserving thresholding: a new approach",
                     journal="Computer Vision, Graphics, and Image Processing", volume="29",
                     pages="377--393", year="1985"),
    "glasbey1993": dict(entry_type="article", author="Glasbey, C. A.",
                        title="An analysis of histogram-based thresholding algorithms",
                        journal="CVGIP: Graphical Models and Image Processing", volume="55", number="6",
                        pages="532--537", year="1993", doi="10.1006/cgip.1993.1040"),
    "prewitt1966": dict(entry_type="article", author="Prewitt, Judith M. S. and Mendelsohn, Mortimer L.",
                        title="The analysis of cell images", journal="Annals of the New York Academy of Sciences",
                        volume="128", pages="1035--1053", year="1966"),
    "doyle1962": dict(entry_type="article", author="Doyle, Worthie",
                      title="Operations useful for similarity-invariant pattern recognition",
                      journal="Journal of the ACM", volume="9", number="2", pages="259--267", year="1962", doi="10.1145/321119.321123"),
}


# ----------------------------------------------------------------------------- Histogramm
def histogram(values: np.ndarray, bitdepth: int) -> tuple[np.ndarray, float, float]:
    """256-Klassen-Histogramm. Liefert (Zaehler, untere Grenze, Klassenbreite)."""
    v = values[np.isfinite(values)].ravel()
    if bitdepth == 8 or v.size == 0:
        h = np.bincount(np.clip(v, 0, 255).astype(np.int64), minlength=256)[:256].astype(np.float64)
        return h, 0.0, 1.0
    lo, hi = float(v.min()), float(v.max())
    if hi <= lo:
        hi = lo + 1.0
    bw = (hi - lo) / 256.0
    idx = np.clip(((v - lo) / bw).astype(np.int64), 0, 255)
    return np.bincount(idx, minlength=256).astype(np.float64), lo, bw


def level_to_value(k: int, lo: float, bw: float) -> float:
    """Klassenindex k -> erster Grauwert oberhalb der Schwelle."""
    return lo + (k + 1) * bw


# ----------------------------------------------------------------------------- Methoden
def _default(d):
    d = d.copy()
    n = len(d)
    d[0] = 0
    d[n - 1] = 0
    nz = np.nonzero(d)[0]
    if nz.size == 0 or nz[0] >= nz[-1]:
        return n // 2
    mn, mx = int(nz[0]), int(nz[-1])
    i = np.arange(n, dtype=np.float64)
    moving = mn
    result = float(mn)
    while True:
        s1 = (i[mn:moving + 1] * d[mn:moving + 1]).sum()
        s2 = d[mn:moving + 1].sum()
        s3 = (i[moving + 1:mx + 1] * d[moving + 1:mx + 1]).sum()
        s4 = d[moving + 1:mx + 1].sum()
        if s2 > 0 and s4 > 0:
            result = (s1 / s2 + s3 / s4) / 2.0
        moving += 1
        if not ((moving + 1) <= result and moving < mx - 1):
            break
    return int(round(result))


def _isodata(d):
    i = np.arange(len(d), dtype=np.float64)
    tot = d.sum()
    if tot == 0:
        return len(d) // 2
    t = int(round((i * d).sum() / tot))
    for _ in range(1000):
        lo, hi = d[:t + 1], d[t + 1:]
        if lo.sum() == 0 or hi.sum() == 0:
            break
        m1 = (i[:t + 1] * lo).sum() / lo.sum()
        m2 = (i[t + 1:] * hi).sum() / hi.sum()
        nt = int(round((m1 + m2) / 2))
        if nt == t:
            break
        t = nt
    return t


def _otsu(d):
    p = d / max(d.sum(), 1)
    i = np.arange(len(d))
    w0 = np.cumsum(p)
    mu = np.cumsum(p * i)
    mut = mu[-1]
    with np.errstate(divide="ignore", invalid="ignore"):
        sb = (mut * w0 - mu) ** 2 / (w0 * (1 - w0))
    sb[~np.isfinite(sb)] = -1
    return int(np.argmax(sb))


def _triangle(d):
    d = d.astype(np.float64).copy()
    n = len(d)
    nz = np.nonzero(d)[0]
    if nz.size == 0:
        return n // 2
    mn = int(nz[0]) - 1 if nz[0] > 0 else 0
    mn2 = int(nz[-1]) + 1 if nz[-1] < n - 1 else n - 1
    dmax = int(np.argmax(d))
    inverted = False
    if (dmax - mn) < (mn2 - dmax):
        inverted = True
        d = d[::-1].copy()
        mn = n - 1 - mn2
        dmax = n - 1 - dmax
    if mn == dmax:
        return mn
    nx = d[dmax]
    ny = mn - dmax
    dist = math.hypot(nx, ny)
    nx, ny = nx / dist, ny / dist
    c = nx * mn + ny * d[mn]
    idx = np.arange(mn + 1, dmax + 1)
    dd = nx * idx + ny * d[mn + 1:dmax + 1] - c
    split = int(idx[np.argmax(dd)]) if dd.size and dd.max() > 0 else mn
    split -= 1
    if inverted:
        return n - 1 - split
    return split


def _li(d):
    i = np.arange(len(d), dtype=np.float64)
    tot = d.sum()
    if tot == 0:
        return len(d) // 2
    mean = (i * d).sum() / tot
    new = mean
    for _ in range(1000):
        old = new
        t = int(old + 0.5)
        lo, hi = d[:t + 1], d[t + 1:]
        mb = (i[:t + 1] * lo).sum() / lo.sum() if lo.sum() > 0 else 0.0
        mo = (i[t + 1:] * hi).sum() / hi.sum() if hi.sum() > 0 else 0.0
        if mb <= 0 or mo <= 0 or mb == mo:
            break
        temp = (mb - mo) / (math.log(mb) - math.log(mo))
        new = int(temp - 0.5) if temp < -2.220446049250313e-16 else int(temp + 0.5)
        if abs(new - old) <= 0.5:
            break
    return int(new)


def _huang(d):
    nz = np.nonzero(d)[0]
    if nz.size == 0:
        return len(d) // 2
    first, last = int(nz[0]), int(nz[-1])
    if first == last:
        return first
    i = np.arange(len(d), dtype=np.float64)
    S = np.cumsum(d)
    W = np.cumsum(i * d)
    C = float(last - first)
    k = np.arange(last - first + 1, dtype=np.float64)
    mu = 1.0 / (1.0 + k / C)
    with np.errstate(divide="ignore", invalid="ignore"):
        smu = -mu * np.log(mu) - (1 - mu) * np.log(1 - mu)
    smu[~np.isfinite(smu)] = 0
    best, emin = first, np.inf
    idx = np.arange(first, last + 1)
    for t in range(first, last):
        m1 = int(round(W[t] / S[t])) if S[t] > 0 else first
        den = S[last] - S[t]
        m2 = int(round((W[last] - W[t]) / den)) if den > 0 else last
        lo = idx[idx <= t]
        hi = idx[idx > t]
        ent = (smu[np.abs(lo - m1)] * d[lo]).sum() + (smu[np.abs(hi - m2)] * d[hi]).sum()
        if ent < emin:
            emin, best = ent, t
    return best


def _maxentropy(d):
    p = d / max(d.sum(), 1)
    P1 = np.cumsum(p)
    P2 = 1.0 - P1
    eps = np.finfo(float).eps
    nzf = np.nonzero(np.abs(P1) >= eps)[0]
    nzl = np.nonzero(np.abs(P2) >= eps)[0]
    if nzf.size == 0 or nzl.size == 0:
        return len(d) // 2
    first, last = int(nzf[0]), int(nzl[-1])
    best, emax = first, -np.inf
    for t in range(first, last + 1):
        a = p[:t + 1][p[:t + 1] > 0] / P1[t] if P1[t] > 0 else np.array([])
        b = p[t + 1:][p[t + 1:] > 0] / P2[t] if P2[t] > 0 else np.array([])
        e = -(a * np.log(a)).sum() - (b * np.log(b)).sum()
        if e > emax:
            emax, best = e, t
    return best


def _yen(d):
    p = d / max(d.sum(), 1)
    P1 = np.cumsum(p)
    P1sq = np.cumsum(p * p)
    P2sq = np.concatenate([np.cumsum((p * p)[::-1])[::-1][1:], [0.0]])
    with np.errstate(divide="ignore", invalid="ignore"):
        a = np.where(P1sq * P2sq > 0, np.log(P1sq * P2sq), 0.0)
        b = np.where(P1 * (1 - P1) > 0, np.log(P1 * (1 - P1)), 0.0)
    crit = -a + 2 * b
    return int(np.argmax(crit))


def _moments(d):
    tot = d.sum()
    if tot == 0:
        return len(d) // 2
    h = d / tot
    i = np.arange(len(d), dtype=np.float64)
    m0, m1, m2, m3 = 1.0, (i * h).sum(), (i * i * h).sum(), (i ** 3 * h).sum()
    cd = m0 * m2 - m1 * m1
    if cd == 0:
        return int(m1)
    c0 = (-m2 * m2 + m1 * m3) / cd
    c1 = (m0 * -m3 + m2 * m1) / cd
    disc = max(c1 * c1 - 4 * c0, 0.0)
    z0 = 0.5 * (-c1 - math.sqrt(disc))
    z1 = 0.5 * (-c1 + math.sqrt(disc))
    if z1 == z0:
        return int(m1)
    p0 = (z1 - m1) / (z1 - z0)
    # Tsai: Schwelle = p0-Quantil, d. h. die kleinste Klasse k mit kumuliertem Anteil >= p0 (Toleranz fuer
    # Rundung); ein Zweiwertbild wird so genau in seine beiden Werte geteilt.
    cs = np.cumsum(h)
    over = np.nonzero(cs >= p0 - 1e-9)[0]
    return int(over[0]) if over.size else len(d) - 1


def _mean(d):
    tot = d.sum()
    if tot == 0:
        return len(d) // 2
    return int(math.floor((np.arange(len(d)) * d).sum() / tot))


def _bimodal(y):
    return int(((y[1:-1] > y[:-2]) & (y[1:-1] > y[2:])).sum()) == 2


def _smooth_until_bimodal(d):
    y = d.astype(np.float64).copy()
    for _ in range(10000):
        if _bimodal(y):
            return y
        p = np.concatenate([[y[0]], y, [y[-1]]])
        y = (p[:-2] + p[1:-1] + p[2:]) / 3.0
    return None


def _minimum(d):
    """Prewitt & Mendelsohn: Tal zwischen den beiden Maxima des bis zur Zweigipfligkeit geglaetteten Histogramms
    (erstes lokales Minimum zwischen den Gipfeln; ein abfallender Anfang vor dem ersten Gipfel zaehlt nicht)."""
    y = _smooth_until_bimodal(d)
    if y is None:
        return _default(d)
    peaks = np.nonzero((y[1:-1] > y[:-2]) & (y[1:-1] > y[2:]))[0] + 1
    p0, p1 = int(peaks[0]), int(peaks[1])
    for k in range(p0 + 1, p1):
        if y[k - 1] > y[k] and y[k + 1] >= y[k]:
            return k
    return p0 + int(np.argmin(y[p0:p1 + 1]))


def _intermodes(d):
    y = _smooth_until_bimodal(d)
    if y is None:
        return _default(d)
    peaks = np.nonzero((y[1:-1] > y[:-2]) & (y[1:-1] > y[2:]))[0] + 1
    return int(math.floor((peaks[0] + peaks[1]) / 2.0))


def _percentile(d, ptile=0.5):
    tot = d.sum()
    if tot == 0:
        return len(d) // 2
    return int(np.argmin(np.abs(np.cumsum(d) / tot - ptile)))


_FUN = {"default": _default, "isodata": _isodata, "otsu": _otsu, "triangle": _triangle, "li": _li,
        "huang": _huang, "maxentropy": _maxentropy, "yen": _yen, "moments": _moments, "mean": _mean,
        "minimum": _minimum, "intermodes": _intermodes, "percentile": _percentile}


def auto_level(hist: np.ndarray, method: str) -> int:
    if method not in _FUN:
        raise ValueError(f"Unbekannte Schwellenmethode: {method}")
    k = int(_FUN[method](np.asarray(hist, dtype=np.float64)))
    return max(0, min(254, k))


def auto_range(values: np.ndarray, bitdepth: int, method: str, dark: bool) -> dict:
    """Schwellenbereich [lo, hi] in Grauwerten fuer Objekte auf dunklem (dark=True) oder hellem Hintergrund."""
    hist, lo, bw = histogram(values, bitdepth)
    k = auto_level(hist, method)
    t = level_to_value(k, lo, bw)
    v = values[np.isfinite(values)]
    vmin, vmax = (float(v.min()), float(v.max())) if v.size else (0.0, 255.0)
    if bitdepth == 8:
        vmin, vmax = min(vmin, 0.0), max(vmax, 255.0)
    if dark:
        rng = (t, vmax)
    else:
        rng = (vmin, t - (1.0 if bitdepth == 8 else bw * 1e-6))
    return {"lo": float(rng[0]), "hi": float(rng[1]), "level": k, "value": float(t), "method": method}
