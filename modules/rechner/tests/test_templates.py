"""Runs the node test of the equation templates; skipped where the bundled Node is not present."""
import shutil
import subprocess
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def node_exe():
    for p in (ROOT / "tools" / "node" / "node.exe", ROOT / "tools" / "node" / "bin" / "node"):
        if p.exists():
            return str(p)
    return shutil.which("node")


class Templates(unittest.TestCase):
    def test_serialisation_round_trip(self):
        exe = node_exe()
        if not exe:
            self.skipTest("Node not available")
        r = subprocess.run([exe, str(HERE / "test_templates.js")], capture_output=True, text=True, encoding="utf-8", timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr or r.stdout)
        self.assertIn("templates OK", r.stdout)


if __name__ == "__main__":
    unittest.main()
