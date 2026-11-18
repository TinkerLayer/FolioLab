"""Minimaler Leser für R-Dateien (.rds, XDR-Serialisierung Version 2/3), nur Daten: Vektoren, Listen, Attribute,
data.table/data.frame, ALTREP-Kompaktformen. Es wird kein R-Code ausgeführt; Funktionen, Umgebungen und externe Zeiger
werden übersprungen bzw. als Platzhalter gelesen.

    obj = read_rds(path)       # RList (Liste mit .names/.attrs), numpy-Arrays, Python-Listen von str
"""
from __future__ import annotations

import bz2
import gzip
import lzma
import struct

import numpy as np

NA_INT = -2147483648


class RList(list):
    """R-Liste: Elemente in Reihenfolge, Namen und Attribute zusätzlich."""

    def __init__(self, items, attrs=None):
        super().__init__(items)
        self.attrs = attrs or {}

    @property
    def names(self):
        return self.attrs.get("names") or [None] * len(self)

    def get(self, key, default=None):
        n = self.names
        return self[n.index(key)] if key in n else default

    def __repr__(self):
        return f"RList({len(self)}, names={self.names[:12]}, class={self.attrs.get('class')})"


class RVec:
    """Atomarer Vektor mit Attributen (z. B. Faktoren, Matrizen)."""

    def __init__(self, data, attrs):
        self.data, self.attrs = data, attrs

    def __repr__(self):
        return f"RVec({type(self.data).__name__}, len={len(self.data)}, attrs={list(self.attrs)})"


class _Sym(str):
    pass


class _Reader:
    def __init__(self, b: bytes):
        self.b, self.p, self.refs = b, 0, []

    def int(self):
        v = struct.unpack_from(">i", self.b, self.p)[0]
        self.p += 4
        return v

    def length(self):
        n = self.int()
        if n == -1:
            hi, lo = self.int(), self.int()
            n = (hi << 32) + (lo & 0xFFFFFFFF)
        return n

    def raw(self, n):
        v = self.b[self.p:self.p + n]
        self.p += n
        return v

    def attrs_of(self, pl):
        """Pairlist (Liste von (tag, wert)) -> dict."""
        out = {}
        for tag, val in pl or []:
            v = val
            if isinstance(v, RVec) and not v.attrs:
                v = v.data
            out[str(tag)] = v
        return out

    def item(self):
        flags = self.int()
        t = flags & 0xFF
        has_attr, has_tag = bool(flags & (1 << 9)), bool(flags & (1 << 10))
        if t == 254:                    # NILVALUE
            return None
        if t in (242, 241, 253, 252, 251, 250):   # Umgebungen, Platzhalter
            return None
        if t == 255:                    # REFSXP
            i = flags >> 8
            if i == 0:
                i = self.int()
            return self.refs[i - 1]
        if t in (247, 248, 249):        # PERSIST / PACKAGE / NAMESPACE
            self.int()
            n = self.int()
            v = [self.item() for _ in range(n)]
            self.refs.append(("ns", v))
            return self.refs[-1]
        if t == 1:                      # SYMSXP
            s = _Sym(self.item() or "")
            self.refs.append(s)
            return s
        if t in (2, 6, 3, 5, 17, 239, 240):   # Paarlisten, Sprache, Closures
            out = []
            attrs = None
            while True:
                if has_attr:
                    attrs = self.item()
                tag = self.item() if has_tag else None
                car = self.item()
                out.append((tag, car))
                flags = self.int()
                t2 = flags & 0xFF
                if t2 == 254:
                    break
                if t2 not in (2, 6, 3, 5, 17, 239, 240):
                    self.p -= 4
                    out.append((None, self.item()))
                    break
                has_attr, has_tag = bool(flags & (1 << 9)), bool(flags & (1 << 10))
            _ = attrs
            return out
        if t == 4:                      # ENVSXP
            self.int()
            ph = ("env",)
            self.refs.append(ph)
            self.item(), self.item(), self.item(), self.item()
            return ph
        if t == 22:                     # EXTPTRSXP
            ph = ("extptr",)
            self.refs.append(ph)
            self.item(), self.item()
            if has_attr:
                self.item()
            return ph
        if t == 23:                     # WEAKREFSXP
            ph = ("weakref",)
            self.refs.append(ph)
            if has_attr:
                self.item()
            return ph
        if t in (7, 8):                 # SPECIAL/BUILTIN
            self.raw(self.int())
            return None
        if t == 9:                      # CHARSXP
            n = self.int()
            if n == -1:
                return None
            s = self.raw(n)
            enc = "latin-1" if flags & (1 << 14) else "utf-8"
            return s.decode(enc, "replace")
        if t == 238:                    # ALTREP
            info = self.item()
            state = self.item()
            attr = self.item()
            cls = str(info[0][1]) if info else ""
            data = self._altrep(cls, state)
            return self._wrap(data, self.attrs_of(attr) if attr else {})
        if t in (10, 13):               # LGL/INT
            n = self.length()
            data = np.frombuffer(self.b, ">i4", n, self.p).astype(np.int32)
            self.p += 4 * n
        elif t == 14:                   # REAL
            n = self.length()
            data = np.frombuffer(self.b, ">f8", n, self.p).astype(np.float64)
            self.p += 8 * n
        elif t == 15:                   # CPLX
            n = self.length()
            data = np.frombuffer(self.b, ">f8", 2 * n, self.p).astype(np.float64).view(np.complex128)
            self.p += 16 * n
        elif t == 24:                   # RAW
            data = self.raw(self.length())
        elif t == 16:                   # STRSXP
            n = self.length()
            data = [self.item() for _ in range(n)]
        elif t in (19, 20):             # VECSXP/EXPRSXP
            n = self.length()
            data = RList([self.item() for _ in range(n)])
        elif t == 25:                   # S4
            data = RList([])
        else:
            raise ValueError(f"RDS: Typ {t} an Position {self.p} wird nicht unterstützt")
        attrs = self.attrs_of(self.item()) if has_attr else {}
        return self._wrap(data, attrs)

    @staticmethod
    def _wrap(data, attrs):
        if isinstance(data, RList):
            data.attrs = attrs
            return data
        if attrs:
            return RVec(data, attrs)
        return data

    def _altrep(self, cls, state):
        if cls == "compact_intseq":
            n, start, inc = (float(v) for v in np.asarray(state)[:3])
            return (start + inc * np.arange(int(n))).astype(np.int32)
        if cls == "compact_realseq":
            n, start, inc = (float(v) for v in np.asarray(state)[:3])
            return start + inc * np.arange(int(n))
        if cls.startswith("wrap_"):
            v = state[0] if isinstance(state, (list, RList)) else state
            return v.data if isinstance(v, RVec) else v
        if cls == "deferred_string":
            v = state[0][1] if isinstance(state, list) and state and isinstance(state[0], tuple) else state
            v = v.data if isinstance(v, RVec) else v
            return [None if (isinstance(a, (int, np.integer)) and a == NA_INT) else (f"{a:g}" if isinstance(a, float) else str(a))
                    for a in np.asarray(v).tolist()]
        raise ValueError(f"RDS: ALTREP-Klasse {cls} wird nicht unterstützt")


def read_rds(path) -> object:
    with open(path, "rb") as f:
        b = f.read()
    if b[:2] == b"\x1f\x8b":
        b = gzip.decompress(b)
    elif b[:3] == b"BZh":
        b = bz2.decompress(b)
    elif b[:6] == b"\xfd7zXZ\x00":
        b = lzma.decompress(b)
    if b[:2] != b"X\n":
        raise ValueError("RDS: nur XDR-Format (X) wird unterstützt")
    r = _Reader(b)
    r.p = 2
    ver = r.int()
    r.int(), r.int()
    if ver == 3:
        r.raw(r.int())
    return r.item()
