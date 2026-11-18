"""A4: Reihenfolge, Zyklen und veraltete Folgewerte."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import labdeps as D  # noqa: E402


class Deps(unittest.TestCase):
    def test_order_and_downstream(self):
        g = {"c": {"b"}, "b": {"a", "x"}, "a": set(), "d": {"a"}}
        o = D.order(g)
        self.assertLess(o.index("a"), o.index("b"))
        self.assertLess(o.index("b"), o.index("c"))
        self.assertEqual(D.downstream(g, "a"), {"b", "c", "d"})
        self.assertEqual(D.downstream(g, "x"), {"b", "c"})
        self.assertEqual(D.in_cycles(g), set())

    def test_cycle_detected(self):
        g = {"a": {"b"}, "b": {"c"}, "c": {"a"}, "d": {"a"}, "e": {"e"}}
        with self.assertRaises(D.CycleError) as cm:
            D.order(g)
        self.assertEqual(cm.exception.cycle[0], cm.exception.cycle[-1])
        self.assertIn("Zirkelbezug", str(cm.exception))
        self.assertEqual(D.in_cycles(g), {"a", "b", "c", "e"})


if __name__ == "__main__":
    unittest.main()
