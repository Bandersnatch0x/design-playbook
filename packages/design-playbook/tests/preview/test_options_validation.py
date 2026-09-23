#!/usr/bin/env python3
"""D-1 / UI-1 / UI-2 regression tests (2026-09-22 alert-rules-page rerun)."""
from __future__ import annotations

import os
import socket
import sys
import unittest
from http.server import BaseHTTPRequestHandler
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[2]
if str(PACKAGE) not in sys.path:
    sys.path.insert(0, str(PACKAGE))

from design_playbook.mcp.preview import review_session  # noqa: E402
from design_playbook.mcp.preview.control import _build_control  # noqa: E402
from design_playbook.mcp.preview.review_session import (  # noqa: E402
    _bind_preview_server,
)
from design_playbook.mcp.preview.server import (  # noqa: E402
    _validate_preview_args,
)

ARGS = {"summary": "s", "round": 1, "report_ref": "r"}


class CustomOptionsValidationTests(unittest.TestCase):
    """D-1: custom options without a known confirm label are rejected."""

    def test_custom_options_without_confirm_label_rejected(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            _validate_preview_args(
                {**ARGS, "options": ["确认方向", "需要修改"]}
            )
        self.assertIn("known confirm label", str(ctx.exception))

    def test_custom_options_keeping_one_confirm_label_accepted(self) -> None:
        _, _, _, _, _, options = _validate_preview_args(
            {**ARGS, "options": ["确认签署决策", "需要修改"]}
        )
        self.assertEqual(options, ["确认签署决策", "需要修改"])

    def test_omitted_options_use_defaults(self) -> None:
        _, _, _, _, _, options = _validate_preview_args(dict(ARGS))
        self.assertEqual(len(options), 2)


class ControlDedupTests(unittest.TestCase):
    """UI-1: the promoted primary option renders only in the primary slots."""

    def test_custom_primary_not_duplicated_in_secondary_row(self) -> None:
        html = _build_control(1, "s", ["确认方向", "需要修改"])
        # header approve + drawer foot = the two primary slots, no more.
        self.assertEqual(html.count('value="确认方向"'), 2)
        self.assertEqual(html.count('value="需要修改"'), 1)

    def test_default_options_unchanged(self) -> None:
        import html as html_lib

        from design_playbook.mcp.preview.i18n import default_options

        options = default_options()
        html = _build_control(1, "s", options)
        confirm_val = html_lib.escape(options[0], quote=True)
        revise_val = html_lib.escape(options[1], quote=True)
        self.assertEqual(html.count(f'value="{confirm_val}"'), 2)
        self.assertEqual(html.count(f'value="{revise_val}"'), 1)


class PreviewPortTests(unittest.TestCase):
    """UI-2: fixed default port keeps origin (and localStorage) stable."""

    def setUp(self) -> None:
        self._old = os.environ.pop("DESIGN_PLAYBOOK_PREVIEW_PORT", None)

    def tearDown(self) -> None:
        if self._old is not None:
            os.environ["DESIGN_PLAYBOOK_PREVIEW_PORT"] = self._old

    def test_default_port_is_fixed(self) -> None:
        # 常量钉死默认端口语义（不绑定——Windows 保留端口段会让硬绑 4619 变脆）
        self.assertEqual(review_session.DEFAULT_PREVIEW_PORT, 4619)
        self.assertNotEqual(review_session.DEFAULT_PREVIEW_PORT, 0)
        # 行为面：env 指定的可用端口被精确绑定
        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        free_port = probe.getsockname()[1]
        probe.close()
        os.environ["DESIGN_PLAYBOOK_PREVIEW_PORT"] = str(free_port)
        try:
            server = _bind_preview_server(BaseHTTPRequestHandler)
            try:
                self.assertEqual(server.server_address[1], free_port)
            finally:
                server.server_close()
        finally:
            os.environ.pop("DESIGN_PLAYBOOK_PREVIEW_PORT", None)

    def test_occupied_default_falls_back_to_ephemeral(self) -> None:
        blocker = socket.socket()
        blocker.bind(("127.0.0.1", 0))
        taken = blocker.getsockname()[1]
        blocker.listen(1)
        os.environ["DESIGN_PLAYBOOK_PREVIEW_PORT"] = str(taken)
        try:
            server = _bind_preview_server(BaseHTTPRequestHandler)
            try:
                self.assertNotEqual(server.server_address[1], taken)
            finally:
                server.server_close()
        finally:
            os.environ.pop("DESIGN_PLAYBOOK_PREVIEW_PORT", None)
            blocker.close()


if __name__ == "__main__":
    unittest.main()
