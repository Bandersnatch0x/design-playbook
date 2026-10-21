"""WB: renderAssets() reaches a row's cells by position, so pin the row shape."""
from __future__ import annotations

import re
import unittest
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "design_playbook_workbench" / "web"


class AssetRowContractTest(unittest.TestCase):
    def test_template_row_nests_button_then_name_then_meta(self) -> None:
        html = (WEB / "app.html").read_text(encoding="utf-8")
        m = re.search(r'<template id="asset-template">(.*?)</template>', html, re.S)
        self.assertIsNotNone(m, "#asset-template is the source of the list rows")
        row = m.group(1)
        self.assertRegex(
            row,
            r'<li[^>]*class="asset-item"[^>]*>\s*'
            r'<button[^>]*class="asset-select"[^>]*>\s*'
            r'<span[^>]*class="asset-name"[^>]*>\s*</span>\s*'
            r'<span[^>]*class="asset-meta"[^>]*>\s*</span>\s*'
            r"</button>\s*</li>",
        )
