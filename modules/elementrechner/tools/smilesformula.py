"""Verschoben nach labcalc.smiles (auch zur Laufzeit gebraucht: Ionen eines Salzes für Ksp aus ΔfG°)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "sdk" / "python"))
from labcalc.smiles import *  # noqa: E402,F401,F403
from labcalc.smiles import SmilesError, base_element, equation_formula, fragment_counts, ion_formula  # noqa: E402,F401