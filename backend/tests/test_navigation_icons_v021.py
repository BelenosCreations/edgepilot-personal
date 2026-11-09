"""Regression: five accessible icon + text nav buttons in hosted Android/PWA UI."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HTML = (ROOT / "backend/static/index.html").read_text(encoding="utf-8")
JS = (ROOT / "backend/static/assets/app.js").read_text(encoding="utf-8")


class NavigationIconTests(unittest.TestCase):
    def test_five_tabs_have_unique_inline_svg_icons_and_labels(self):
        nav = HTML.split('<nav class="nav" aria-label="Main navigation">', 1)[1].split("</nav>", 1)[0]
        buttons = re.findall(r'<button\\b[^>]*data-nav="([^"]+)"[^>]*>(.*?)</button>', nav, re.S)
        self.assertEqual([key for key, _ in buttons], ["dash", "auto", "micro", "fifteen", "more"])
        for (_, inner), label in zip(buttons, ["Overview", "Auto-Trade", "Micro-Trade", "15-Minute", "More"]):
            self.assertEqual(inner.count('<svg class="nav-icon"'), 1)
            self.assertIn('aria-hidden="true"', inner)
            self.assertIn('focusable="false"', inner)
            self.assertIn('<span class="nav-label">' + label + '</span>', inner)
            self.assertTrue("<path " in inner or "<circle " in inner or "<rect " in inner)
        self.assertEqual(len(set(inner.split("</svg>", 1)[0] for _, inner in buttons)), 5)

    def test_selected_tab_updates_icon_label_and_accessibility_state(self):
        self.assertIn(".nav button.active-nav", HTML)
        self.assertIn("b.classList.toggle('active-nav',selected)", JS)
        self.assertIn("b.setAttribute('aria-current','page')", JS)
        self.assertIn("b.removeAttribute('aria-current')", JS)
        self.assertIn("data-nav=\"dash\" onclick=\"tab('dash')\" aria-current=\"page\"", HTML)
        self.assertIn("display:flex;flex-direction:column;align-items:center", HTML)
        self.assertIn(".nav-icon{display:block;width:22px;height:22px", HTML)
        self.assertIn("white-space:nowrap", HTML)


if __name__ == "__main__":
    unittest.main()
