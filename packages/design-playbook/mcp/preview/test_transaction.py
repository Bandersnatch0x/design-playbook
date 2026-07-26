#!/usr/bin/env python3
"""Contract tests for the Preview decision transaction."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from transaction import run_preview_transaction  # noqa: E402


class PreviewDecisionTransactionTests(unittest.TestCase):
    def test_confirm_pass_commits_confirm_and_audit_artifacts(self) -> None:
        seen: list[tuple[Path, str, list[str], int]] = []

        def collect(
            prototype: Path, summary: str, options: list[str], round_n: int
        ) -> dict:
            seen.append((prototype, summary, options, round_n))
            return {
                "choice": "确认通过",
                "feedback": "层级清晰",
                "anchors": [],
                "aborted": False,
            }

        with tempfile.TemporaryDirectory() as tmp:
            prototype = Path(tmp) / "round-1.html"
            prototype.write_text("<html><body>reviewed</body></html>", encoding="utf-8")

            result = run_preview_transaction(
                path_arg=str(prototype),
                html=None,
                summary="  review hierarchy  ",
                round_n=1,
                report_ref="  report.md  ",
                options=["确认通过", "需要修改"],
                collect=collect,
            )

            confirm_path = Path(result["confirm_record_path"])
            confirm = json.loads(confirm_path.read_text(encoding="utf-8"))
            log = (Path(tmp) / "log.md").read_text(encoding="utf-8")

        self.assertEqual(
            seen,
            [(prototype, "review hierarchy", ["确认通过", "需要修改"], 1)],
        )
        self.assertEqual(
            result,
            {
                "confirmed": True,
                "floor_pass": True,
                "selected_options": ["确认通过"],
                "feedback": "层级清晰",
                "anchors": [],
                "round": 1,
                "confirm_record_path": str(confirm_path),
                "aborted": False,
            },
        )
        self.assertTrue(confirm["confirmed"])
        self.assertTrue(confirm["floor_pass"])
        self.assertEqual(confirm["selected_options"], ["确认通过"])
        self.assertIn("- selected: 确认通过", log)
        self.assertIn("- floor_pass: true", log)

    def test_confirm_floor_failure_records_non_authoritative_attempt(self) -> None:
        result, confirm, log = self._run_submission(
            {"choice": "确认通过", "feedback": "", "anchors": [], "aborted": False}
        )

        self.assertFalse(result["confirmed"])
        self.assertFalse(result["floor_pass"])
        self.assertTrue(confirm["confirmed"] is False)
        self.assertIn("confirm with no substantive feedback", confirm["floor_failure"])
        self.assertIn("- floor_pass: false", log)

    def test_revise_is_audited_without_confirm_record(self) -> None:
        result, confirm, log = self._run_submission(
            {"choice": "需要修改", "feedback": "调整间距", "anchors": [], "aborted": False}
        )

        self.assertFalse(result["confirmed"])
        self.assertTrue(result["floor_pass"])
        self.assertEqual(result["selected_options"], ["需要修改"])
        self.assertIsNone(confirm)
        self.assertIn("- selected: 需要修改", log)

    def test_abort_is_audited_without_confirm_record(self) -> None:
        result, confirm, log = self._run_submission(
            {"choice": "__abort__", "feedback": "", "anchors": [], "aborted": True}
        )

        self.assertFalse(result["confirmed"])
        self.assertEqual(result["selected_options"], [])
        self.assertTrue(result["aborted"])
        self.assertIsNone(confirm)
        self.assertIn("- aborted: true", log)

    def test_rejected_submission_fails_closed_and_is_audited(self) -> None:
        result, confirm, log = self._run_submission(
            {
                "choice": "",
                "feedback": "forged",
                "anchors": [],
                "aborted": True,
                "rejected": True,
                "rejection": "invalid_token",
            }
        )

        self.assertFalse(result["confirmed"])
        self.assertFalse(result["floor_pass"])
        self.assertEqual(result["selected_options"], [])
        self.assertIsNone(confirm)
        self.assertIn("- rejected: true", log)
        self.assertIn("- rejection: invalid_token", log)

    def _run_submission(
        self, submission: dict
    ) -> tuple[dict, dict | None, str]:
        def collect(
            prototype: Path, summary: str, options: list[str], round_n: int
        ) -> dict:
            return submission

        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        preview_dir = Path(temp.name)
        prototype = preview_dir / "round-1.html"
        prototype.write_text("<html><body>reviewed</body></html>", encoding="utf-8")
        result = run_preview_transaction(
            path_arg=str(prototype),
            html=None,
            summary="summary",
            round_n=1,
            report_ref="report.md",
            options=["确认通过", "需要修改"],
            collect=collect,
        )
        confirm_path = preview_dir / "confirm-round-1.json"
        confirm = (
            json.loads(confirm_path.read_text(encoding="utf-8"))
            if confirm_path.is_file()
            else None
        )
        log = (preview_dir / "log.md").read_text(encoding="utf-8")
        return result, confirm, log


if __name__ == "__main__":
    unittest.main()
