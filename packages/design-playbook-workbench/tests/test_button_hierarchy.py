"""U-10: bare buttons are neutral, one primary per panel, hover/active states exist."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "design_playbook_workbench" / "web"


def _rule(css: str, selector: str) -> str:
    m = re.search(r"(?m)^" + re.escape(selector) + r"\s*\{([^}]*)\}", css)
    return m.group(1) if m else ""


class ButtonHierarchyTest(unittest.TestCase):
    def test_bare_button_is_not_accent_filled(self) -> None:
        css = (WEB / "app.css").read_text(encoding="utf-8")
        self.assertNotIn("--accent)", _rule(css, "button").replace("--accent-ink", ""))

    def test_primary_class_carries_the_accent(self) -> None:
        css = (WEB / "app.css").read_text(encoding="utf-8")
        self.assertIn("var(--accent)", _rule(css, "button.primary"))

    def test_hover_and_active_states_exist(self) -> None:
        css = (WEB / "app.css").read_text(encoding="utf-8")
        self.assertIn("button:hover", css)
        self.assertIn("button:active", css)

    def test_each_panel_has_at_most_one_primary(self) -> None:
        html = (WEB / "app.html").read_text(encoding="utf-8")
        for block in re.split(r"(?=<section class=\"panel)", html):
            n = len(re.findall(r'<button[^>]*class="[^"]*\bprimary\b', block.split("</section>")[0]))
            self.assertLessEqual(n, 1)
        self.assertGreaterEqual(html.count("primary"), 5)
