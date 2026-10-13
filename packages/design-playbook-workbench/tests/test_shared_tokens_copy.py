"""U-07 step 2 + ADR-0048: the workbench shell reads copies of shared files.

``web/tokens.css`` is a byte copy of ``mcp/_shared/tokens.css``; the shell
links it ahead of ``app.css`` and keeps no private palette of its own.
The copy ships beside ``dpbui.lock.json`` and the constructor refuses to
start when the two disagree (ADR-0048, 2026-10-13 amendment).
"""
from __future__ import annotations

import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from design_playbook_workbench.ui import LOCK_NAME, UIResources

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


class SharedLockStartupTest(unittest.TestCase):
    """The constructor fails closed on a drifted or unreadable lock."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        for path in WEB.iterdir():
            if path.is_file():
                shutil.copyfile(path, self.base / path.name)

    def test_a_matching_lock_starts(self) -> None:
        resources = UIResources(self.base)
        self.assertIsNotNone(resources.lookup("/tokens.css"))

    def test_a_drifted_copy_refuses_to_start(self) -> None:
        (self.base / "tokens.css").write_text("drift", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "drifted from its lock"):
            UIResources(self.base)

    def test_a_missing_lock_refuses_to_start(self) -> None:
        (self.base / LOCK_NAME).unlink()
        with self.assertRaisesRegex(RuntimeError, "lock unreadable"):
            UIResources(self.base)

    def test_a_malformed_lock_refuses_to_start(self) -> None:
        (self.base / LOCK_NAME).write_text("{not json", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "lock unreadable"):
            UIResources(self.base)

    def test_a_missing_locked_copy_refuses_to_start(self) -> None:
        (self.base / "tokens.css").unlink()
        with self.assertRaisesRegex(RuntimeError, "copy missing"):
            UIResources(self.base)

    def test_the_lock_covers_tokens_css_with_its_real_digest(self) -> None:
        lock = json.loads((self.base / LOCK_NAME).read_text(encoding="utf-8"))
        self.assertEqual(lock["schemaVersion"], 1)
        import hashlib

        self.assertEqual(
            lock["files"]["tokens.css"],
            hashlib.sha256(SHARED.read_bytes()).hexdigest(),
        )


if __name__ == "__main__":
    unittest.main()
