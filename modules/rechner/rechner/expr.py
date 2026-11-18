"""Verschoben nach sdk/python/labcalc/expr.py (gemeinsam für alle Module). ``rechner.expr`` ist dasselbe Modul."""
import sys
from pathlib import Path

_SDK = Path(__file__).resolve().parents[3] / "sdk" / "python"
if _SDK.is_dir() and str(_SDK) not in sys.path:
    sys.path.insert(0, str(_SDK))

from labcalc import expr as _m  # noqa: E402

sys.modules[__name__] = _m
