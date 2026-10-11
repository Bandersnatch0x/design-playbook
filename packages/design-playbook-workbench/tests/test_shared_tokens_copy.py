"""U-07 step 2: the workbench shell reads a copy of the shared token file.

``web/tokens.css`` is a byte copy of ``mcp/_shared/tokens.css``; the shell
links it ahead of ``app.css`` and keeps no private palette of its own.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

from design_playbook_workbench.ui import UIResources

WEB = Path(__file__).resolve().parents[1] / "design_playbook_workbench" / "web"
SHARED = Path(__file__).resolve().parents[2] / "design-playbook" / "mcp" / "_shared" / "tokens.css"
_DEF = re.compile(r"(--dpb-[\w-]+)\s*:")


class WorkbenchTokenCopyTest(unittest.TestCase):
    def test_copy_is_byte_identical_to_the_shared_file(self) -> None:
        self.assertEqual((WEB / "tokens.css").read_bytes(), SHARED.read_bytes())

    def test_shell_serves_the_copy_with_the_stylesheet_policy(self) -> None:
        resource = UIResources().lookup("/tokens.css")
        assert resource is not None
        self.assertEqual(resource.body, SHARED.read_bytes())
        self.assertEqual(resource.content_type, "text/css; charset=utf-8")
        self.assertIn("default-src 'none'", resource.content_security_policy)

    def test_shell_links_tokens_before_app_css_on_a_ui_root(self) -> None:
        html = (WEB / "app.html").read_text(encoding="utf-8")
        self.assertIn('<html lang="zh-CN" class="dpb-ui">', html)
        self.assertLess(html.index('href="/tokens.css"'), html.index('href="/app.css"'))

    def test_app_css_keeps_no_private_palette(self) -> None:
        css = (WEB / "app.css").read_text(encoding="utf-8")
        self.assertEqual(_DEF.findall(css), [])


if __name__ == "__main__":
    unittest.main()
