"""U-12 (WB): a bordered card never sits inside another bordered card."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "design_playbook_workbench" / "web"


class PanelNestingTest(unittest.TestCase):
    def test_proposal_diff_inside_item_has_no_border(self) -> None:
        css = (WEB / "app.css").read_text(encoding="utf-8")
        m = re.search(r"(?m)^\.proposal-diff\s*\{([^}]*)\}", css)
        self.assertIsNotNone(m)
        self.assertNotRegex(m.group(1), r"border:\s*1px")

    def test_item_template_nests_diff_in_item_only(self) -> None:
        html = (WEB / "app.html").read_text(encoding="utf-8")
        self.assertIn('class="proposal-item"', html)
