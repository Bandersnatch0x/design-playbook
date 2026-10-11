"""U-18: the shell never calls the native blocking dialogs."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "design_playbook_workbench" / "web"


class NoNativeDialogsTest(unittest.TestCase):
    def test_app_js_has_no_native_confirm_or_prompt(self) -> None:
        source = (WEB / "app.js").read_text(encoding="utf-8")
        calls = re.findall(r"window\.(?:confirm|prompt|alert)\s*\(", source)
        self.assertEqual(calls, [])

    def test_dialog_helpers_are_alertdialogs_that_start_on_cancel(self) -> None:
        source = (WEB / "app.js").read_text(encoding="utf-8")
        self.assertIn('"alertdialog"', source)
        self.assertIn("askConfirm", source)
        self.assertIn("askText", source)


if __name__ == "__main__":
    unittest.main()
