"""UI-17: Die Karte auf der Startseite zeigt dasselbe Symbol wie der Kopf der Modulseite.

module.json "icon_svg" (inneres Markup eines 24x24-Strichsymbols) muss dem Symbol in <… class="brand"> der Seite
entsprechen, und es darf nur einfache Formen enthalten (die Startseite verwirft alles andere).
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MODULES = ROOT / "modules"
TAGS = {"path", "circle", "rect", "line", "polyline", "polygon", "ellipse", "g"}
ATTRS = {"d", "cx", "cy", "r", "rx", "ry", "x", "y", "x1", "y1", "x2", "y2", "width", "height", "points", "transform",
         "fill", "opacity", "stroke-width"}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).replace(" />", "/>").strip()


def _page(mod: Path):
    pages = [p for p in mod.rglob("static/index.html") if "tests" not in p.parts]
    return pages[0] if len(pages) == 1 else None


class IconTest(unittest.TestCase):
    def test_card_icon_matches_page(self):
        seen = 0
        for mj in sorted(MODULES.glob("*/module.json")):
            m = json.loads(mj.read_text(encoding="utf-8"))
            if m.get("status") != "ready":
                continue
            with self.subTest(module=m["id"]):
                self.assertIn("icon_svg", m, "module.json braucht icon_svg (Symbol des Seitenkopfs)")
                page = _page(mj.parent)
                self.assertIsNotNone(page, "Seite static/index.html nicht eindeutig")
                html = page.read_text(encoding="utf-8")
                hit = re.search(r'class="brand"[^>]*>\s*<svg[^>]*>(.*?)</svg>', html, re.S)
                self.assertIsNotNone(hit, "kein Symbol im Seitenkopf (class=\"brand\")")
                self.assertEqual(_norm(hit.group(1)), _norm(m["icon_svg"]))
                for tag, attrs in re.findall(r"<([a-z]+)([^>]*)/?>", m["icon_svg"]):
                    self.assertIn(tag, TAGS)
                    for a in re.findall(r'([a-z-]+)="', attrs):
                        self.assertIn(a, ATTRS)
                seen += 1
        self.assertGreaterEqual(seen, 7)


if __name__ == "__main__":
    unittest.main()
