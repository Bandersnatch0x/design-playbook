#!/usr/bin/env python3
"""Focused contract tests for shared MCP tool-result mapping."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _transport import ToolError, _exception_result  # noqa: E402


class TransportToolErrorTests(unittest.TestCase):
    def test_typed_error_preserves_readable_and_structured_content(self) -> None:
        details = {
            "error": "preview_transaction",
            "retryable": True,
            "round": 2,
            "decision_id": "abc",
            "artifact": "decision-round-2.json",
        }
        result = _exception_result(ToolError("repair required", details))

        self.assertTrue(result["isError"])
        self.assertEqual(result["content"][0]["text"], "repair required")
        self.assertEqual(result["structuredContent"], details)

    def test_ordinary_exception_mapping_is_unchanged(self) -> None:
        self.assertEqual(
            _exception_result(ValueError("bad argument")),
            {
                "content": [{"type": "text", "text": "bad argument"}],
                "isError": True,
            },
        )


if __name__ == "__main__":
    unittest.main()
