"""Leser fuer .flps Dateien des IMADA Force Logger Ver2 (Spezifikation Abschnitt 1).

Eine .flps Datei ist ein .NET BinaryFormatter Datenstrom nach MS-NRBF.
Der Leser kommt bewusst nur mit der Standardbibliothek aus.
"""
from __future__ import annotations

import io
import struct
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

# --- Einheitencodes (Abschnitt 1.4) -------------------------------------------
FORCE_UNITS = ["mN", "cN", "N", "kN", "gf", "kgf", "ozf", "lbf"]
DISPLACEMENT_UNITS = ["mm", "cm", "in", "ohne", "µm"]      # 4 = µm: nur Datensätze (I-03), nie im Gerät
# Gesichert ist nur ForceUnit 2 = N
CONFIRMED_FORCE_UNITS = {2}
CONFIRMED_DISPLACEMENT_UNITS: set[int] = set()

# Umrechnung nach Newton fuer die Plausibilitaetspruefung
FORCE_TO_N = {"mN": 1e-3, "cN": 1e-2, "N": 1.0, "kN": 1e3, "gf": 9.80665e-3,
              "kgf": 9.80665, "ozf": 0.278013851, "lbf": 4.448221615}


class FlpsError(Exception):
    pass


class _Ref:
    __slots__ = ("id",)

    def __init__(self, ref_id: int):
        self.id = ref_id


class _Null:
    __slots__ = ("count",)

    def __init__(self, count: int = 1):
        self.count = count


@dataclass
class _ClassDef:
    name: str
    members: list[str]
    binary_types: list[int] | None  # None = untyped (SystemClassWithMembers / ClassWithMembers)
    additional: list


class NrbfReader:
    """Minimaler MS-NRBF Leser. Liefert das Wurzelobjekt mit aufgeloesten Referenzen."""

    def __init__(self, data: bytes):
        self.s = io.BytesIO(data)
        self.objects: dict[int, object] = {}
        self.classes: dict[int, _ClassDef] = {}
        self.root_id: int | None = None

    # -- Primitive --------------------------------------------------------------
    def _read(self, n: int) -> bytes:
        b = self.s.read(n)
        if len(b) != n:
            raise FlpsError("Datei endet unerwartet")
        return b

    def u8(self) -> int:
        return self._read(1)[0]

    def i32(self) -> int:
        return struct.unpack("<i", self._read(4))[0]

    def string(self) -> str:
        # Laenge siebenbitweise codiert mit Fortsetzungsbit
        length, shift = 0, 0
        while True:
            b = self.u8()
            length |= (b & 0x7F) << shift
            if not b & 0x80:
                break
            shift += 7
            if shift > 35:
                raise FlpsError("ungueltige Stringlaenge")
        return self._read(length).decode("utf-8")

    def primitive(self, code: int):
        if code == 1:
            return self.u8() != 0
        if code == 2:
            return self.u8()
        if code == 3:  # Char, UTF-8
            first = self.u8()
            n = 1 if first < 0x80 else 2 if first < 0xE0 else 3 if first < 0xF0 else 4
            return (bytes([first]) + self._read(n - 1)).decode("utf-8")
        if code == 5:  # Decimal als String
            return self.string()
        if code == 6:
            return struct.unpack("<d", self._read(8))[0]
        if code == 7:
            return struct.unpack("<h", self._read(2))[0]
        if code == 8:
            return self.i32()
        if code == 9:
            return struct.unpack("<q", self._read(8))[0]
        if code == 10:
            return struct.unpack("<b", self._read(1))[0]
        if code == 11:
            return struct.unpack("<f", self._read(4))[0]
        if code == 12:  # TimeSpan, Ticks
            return timedelta(microseconds=struct.unpack("<q", self._read(8))[0] / 10)
        if code == 13:
            return self.datetime()
        if code == 14:
            return struct.unpack("<H", self._read(2))[0]
        if code == 15:
            return struct.unpack("<I", self._read(4))[0]
        if code == 16:
            return struct.unpack("<Q", self._read(8))[0]
        if code == 17:
            return None
        if code == 18:
            return self.string()
        raise FlpsError(f"unbekannter Primitivtyp {code}")

    def datetime(self) -> datetime:
        raw = struct.unpack("<Q", self._read(8))[0]
        ticks = raw & ((1 << 62) - 1)
        if ticks & (1 << 61):  # vorzeichenbehaftet erweitern
            ticks -= 1 << 62
        # Kind = raw >> 62 (0 unspecified, 1 UTC, 2 local) - Uhrzeit wird wie gespeichert angezeigt
        return datetime(1, 1, 1) + timedelta(microseconds=ticks // 10)

    # -- Klassen ---------------------------------------------------------------
    def _class_info(self):
        obj_id = self.i32()
        name = self.string()
        count = self.i32()
        members = [self.string() for _ in range(count)]
        return obj_id, name, members

    def _member_type_info(self, count: int):
        types = [self.u8() for _ in range(count)]
        add = []
        for t in types:
            if t in (0, 7):
                add.append(self.u8())
            elif t == 3:
                add.append(self.string())
            elif t == 4:
                add.append((self.string(), self.i32()))
            else:
                add.append(None)
        return types, add

    def _read_members(self, obj_id: int, cdef: _ClassDef) -> dict:
        obj: dict = {"__class__": cdef.name}
        self.objects[obj_id] = obj
        for i, m in enumerate(cdef.members):
            if cdef.binary_types is not None and cdef.binary_types[i] == 0:
                obj[m] = self.primitive(cdef.additional[i])
            else:
                v = self.record()
                if isinstance(v, _Null):
                    v = None
                obj[m] = v
        return obj

    def _read_elements(self, n: int, prim: int | None = None) -> list:
        out: list = []
        while len(out) < n:
            if prim is not None:
                out.append(self.primitive(prim))
                continue
            v = self.record()
            if isinstance(v, _Null):
                out.extend([None] * v.count)
            else:
                out.append(v)
        return out

    # -- Records ---------------------------------------------------------------
    def record(self):
        code = self.u8()
        if code == 0:  # SerializedStreamHeader
            self.root_id = self.i32()
            for _ in range(3):
                self.i32()
            return self.record()
        if code == 1:  # ClassWithId
            obj_id = self.i32()
            meta = self.i32()
            if meta not in self.classes:
                raise FlpsError(f"Klassendefinition {meta} fehlt")
            cdef = self.classes[meta]
            self.classes[obj_id] = cdef
            return self._read_members(obj_id, cdef)
        if code in (2, 3, 4, 5):
            obj_id, name, members = self._class_info()
            if code in (4, 5):
                types, add = self._member_type_info(len(members))
            else:
                types, add = None, [None] * len(members)
            if code in (3, 5):
                self.i32()  # LibraryId
            cdef = _ClassDef(name, members, types, add)
            self.classes[obj_id] = cdef
            return self._read_members(obj_id, cdef)
        if code == 6:  # BinaryObjectString
            obj_id = self.i32()
            val = self.string()
            self.objects[obj_id] = val
            return val
        if code == 7:  # BinaryArray
            obj_id = self.i32()
            atype = self.u8()
            rank = self.i32()
            lengths = [self.i32() for _ in range(rank)]
            if atype in (3, 4, 5):
                for _ in range(rank):
                    self.i32()
            btype = self.u8()
            info = None
            if btype in (0, 7):
                info = self.u8()
            elif btype == 3:
                info = self.string()
            elif btype == 4:
                info = (self.string(), self.i32())
            total = 1
            for n in lengths:
                total *= n
            arr: list = []
            self.objects[obj_id] = arr
            arr.extend(self._read_elements(total, info if btype == 0 else None))
            return arr
        if code == 8:  # MemberPrimitiveTyped
            return self.primitive(self.u8())
        if code == 9:  # MemberReference
            return _Ref(self.i32())
        if code == 10:
            return _Null(1)
        if code == 11:
            raise _MessageEnd()
        if code == 12:  # BinaryLibrary
            self.i32()
            self.string()
            return self.record()
        if code == 13:
            return _Null(self.u8())
        if code == 14:
            return _Null(self.i32())
        if code == 15:  # ArraySinglePrimitive
            obj_id = self.i32()
            n = self.i32()
            prim = self.u8()
            arr = []
            self.objects[obj_id] = arr
            arr.extend(self._read_elements(n, prim))
            return arr
        if code in (16, 17):  # ArraySingleObject / ArraySingleString
            obj_id = self.i32()
            n = self.i32()
            arr = []
            self.objects[obj_id] = arr
            arr.extend(self._read_elements(n))
            return arr
        raise FlpsError(f"unbekannter Record-Typ {code} an Position {self.s.tell() - 1}")

    def read(self):
        try:
            while True:
                self.record()
        except _MessageEnd:
            pass
        if self.root_id is None or self.root_id not in self.objects:
            raise FlpsError("Wurzelobjekt nicht gefunden")
        return self._resolve(self.objects[self.root_id], set())

    def _resolve(self, v, seen: set):
        if isinstance(v, _Ref):
            if v.id not in self.objects:
                return None
            return self._resolve(self.objects[v.id], seen)
        if isinstance(v, dict):
            if id(v) in seen:
                return v
            seen.add(id(v))
            for k in list(v):
                v[k] = self._resolve(v[k], seen)
            # .NET Enums werden als Objekt mit value__ serialisiert
            if set(v) == {"__class__", "value__"}:
                return v["value__"]
            return v
        if isinstance(v, list):
            if id(v) in seen:
                return v
            seen.add(id(v))
            for i, x in enumerate(v):
                v[i] = self._resolve(x, seen)
            return v
        return v


class _MessageEnd(Exception):
    pass


# --- Objektmodell (Abschnitt 1.3) ---------------------------------------------
@dataclass
class Point:
    num: int
    force: float
    force_decimal_point: int | None
    force_unit: int | None
    displacement: int
    displacement_unit: int | None
    timestamp: datetime
    operator_dept: str | None = None
    operator_name: str | None = None
    condition_name: str | None = None
    comparator: object = None
    tilt_result: object = None
    is_empty: bool | None = None


@dataclass
class FlpsFile:
    path: str
    serial_number: str
    model_name: str
    comment: str
    gauge_series: object
    points: list[Point] = field(default_factory=list)
    origin: dict | None = None      # I-03: aus einem Datensatz (Titel, Freigabe, Version, Spalten, Probenmasse)

    # -- Einheiten ---------------------------------------------------------------
    @property
    def force_unit_code(self) -> int | None:
        codes = {p.force_unit for p in self.points if p.force_unit is not None}
        return codes.pop() if len(codes) == 1 else (min(codes) if codes else None)

    @property
    def displacement_unit_code(self) -> int | None:
        codes = {p.displacement_unit for p in self.points if p.displacement_unit is not None}
        return codes.pop() if len(codes) == 1 else (min(codes) if codes else None)

    @property
    def force_unit(self) -> str:
        c = self.force_unit_code
        return FORCE_UNITS[c] if c is not None and 0 <= c < len(FORCE_UNITS) else f"Code {c}"

    @property
    def force_unit_confirmed(self) -> bool:
        return self.force_unit_code in CONFIRMED_FORCE_UNITS

    @property
    def displacement_unit(self) -> str:
        c = self.displacement_unit_code
        return DISPLACEMENT_UNITS[c] if c is not None and 0 <= c < len(DISPLACEMENT_UNITS) else f"Code {c}"

    @property
    def displacement_unit_confirmed(self) -> bool:
        return self.origin is not None or self.displacement_unit_code in CONFIRMED_DISPLACEMENT_UNITS

    def meta_text(self, attr: str) -> str:
        vals = {getattr(p, attr) for p in self.points}
        vals.discard(None)
        return " / ".join(sorted(str(v) for v in vals))

    def plausibility_warning(self) -> str | None:
        """Pruefung aus 1.4: groesste Kraft ueber Messbereich des Geraets -> Zuordnung falsch."""
        import re
        m = re.search(r"-(\d+(?:\.\d+)?)\s*(k?N)", self.model_name or "")
        if not m or not self.points:
            return None
        cap = float(m.group(1)) * (1000.0 if m.group(2) == "kN" else 1.0)
        fmax = max(abs(p.force) for p in self.points)
        factor = FORCE_TO_N.get(self.force_unit)
        if factor is None:
            return f"Einheitencode {self.force_unit_code} unbekannt."
        if fmax * factor > cap * 1.05:
            return (f"Grösste Kraft {fmax:g} {self.force_unit} = {fmax * factor:.4g} N liegt über dem "
                    f"Messbereich {cap:g} N des Modells {self.model_name}: Einheitenzuordnung ist falsch.")
        return None


def _s(v) -> str:
    return "" if v is None else str(v)


def parse_bytes(data: bytes, path: str = "") -> FlpsFile:
    from . import dataset as _ds
    if _ds.is_dataset(data):                     # I-03: Zugversuch aus einem Datensatz (JSON statt NRBF)
        return _ds.parse(data, path)
    root = NrbfReader(data).read()
    if not isinstance(root, dict) or "Data" not in root:
        raise FlpsError("Kein IMADA.SingleSaveData Objekt gefunden")
    pts: list[Point] = []
    for e in root.get("Data") or []:
        if not isinstance(e, dict):
            continue
        pts.append(Point(
            num=int(e.get("Num") or 0),
            force=float(e.get("Force") or 0.0),
            force_decimal_point=e.get("ForceDecimalPoint"),
            force_unit=e.get("ForceUnit"),
            displacement=int(e.get("Displacement") or 0),
            displacement_unit=e.get("DisplacementUnit"),
            timestamp=e.get("DateTime"),
            operator_dept=e.get("OperatorDept"),
            operator_name=e.get("OperatorName"),
            condition_name=e.get("ConditionName"),
            comparator=e.get("Comparator"),
            tilt_result=e.get("TiltResult"),
            is_empty=e.get("IsEmpty"),
        ))
    return FlpsFile(
        path=path,
        serial_number=_s(root.get("SerialNumber")),
        model_name=_s(root.get("ModelName")),
        comment=_s(root.get("Comment")),
        gauge_series=root.get("GaugeSeries"),
        points=pts,
    )


def parse_file(path: str | Path) -> FlpsFile:
    p = Path(path)
    return parse_bytes(p.read_bytes(), str(p))
