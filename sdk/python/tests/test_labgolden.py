"""labgolden: what a golden comparison tolerates and what it still catches."""
import unittest

import labgolden as G


def snap(first="0,0,0,1.16072e-17,elastisch", size=8663):
    return {"bundle": {}, "items": [], "source": {},
            "files": {"data/m.csv": {"type": "csv", "header": "t,F", "rows": 2, "first": first, "last": "1,2"},
                      "fig/a.pdf": {"type": "pdf", "size": size}}}


class Compare(unittest.TestCase):
    def test_float_noise_near_zero_ignored(self):
        # seen in CI: numpy builds give 3.67083e-17 or 1.16072e-17 for a strain that is 0
        self.assertEqual(G.compare(snap(), snap(first="0,0,0,3.67083e-17,elastisch")), "")

    def test_real_number_change_caught(self):
        self.assertIn("first", G.compare(snap(first="0,0,0,0.0012,elastisch"), snap(first="0,0,0,0.0013,elastisch")))

    def test_seventh_digit_ignored(self):
        self.assertEqual(G.compare(snap(first="1.0000001,2"), snap(first="1.0000002,2")), "")

    def test_figure_size_between_matplotlib_releases(self):
        # seen in CI: 8663 B (matplotlib on Python 3.10) vs 12177 B reference
        self.assertEqual(G.compare(snap(size=8663), snap(size=12177)), "")

    def test_empty_figure_caught(self):
        self.assertIn("factor", G.compare(snap(size=3000), snap(size=12177)))
        self.assertIn("factor", G.compare(snap(size=30000), snap(size=12177)))

    def test_stored_text_unchanged(self):
        # normalising happens on copies; the snapshot keeps the original row
        s = snap()
        G.compare(s, snap(first="0,0,0,3.67083e-17,elastisch"))
        self.assertEqual(s["files"]["data/m.csv"]["first"], "0,0,0,1.16072e-17,elastisch")


if __name__ == "__main__":
    unittest.main()
