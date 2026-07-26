#!/usr/bin/env python3
"""Contract tests for the Preview decision transaction."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import transaction  # noqa: E402
from transaction import TransactionConflict, run_preview_transaction  # noqa: E402


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
                "decision_id": result["decision_id"],
            },
        )
        self.assertEqual(len(result["decision_id"]), 32)
        self.assertEqual(confirm["decision_id"], result["decision_id"])
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

    def test_same_binding_retry_repairs_without_collecting_again(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            prototype = Path(tmp) / "round-1.html"
            prototype.write_text("reviewed", encoding="utf-8")
            calls = 0

            def collect(*args: object) -> dict:
                nonlocal calls
                calls += 1
                return {
                    "choice": "确认通过", "feedback": "清晰",
                    "anchors": [], "aborted": False,
                }

            first = self._run(prototype, collect=collect)
            (Path(tmp) / "confirm-round-1.json").unlink()
            (Path(tmp) / "log.md").write_text("corrupt projection", encoding="utf-8")
            repaired = self._run(prototype, collect=collect)

            self.assertEqual(calls, 1)
            self.assertEqual(repaired["decision_id"], first["decision_id"])
            self.assertTrue(Path(repaired["confirm_record_path"]).is_file())
            log = (Path(tmp) / "log.md").read_text(encoding="utf-8")
            self.assertEqual(log.count(first["decision_id"]), 1)
            self.assertNotIn("corrupt projection", log)

    def test_changed_binding_and_legacy_confirm_fail_closed(self) -> None:
        variants = (
            {"summary": "changed"},
            {"report_ref": "other.md"},
            {"options": ["需要修改", "确认通过"]},
        )
        for variant in variants:
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as tmp:
                prototype = Path(tmp) / "round-1.html"
                prototype.write_text("reviewed", encoding="utf-8")
                self._run(prototype)
                with self.assertRaisesRegex(TransactionConflict, "use next round"):
                    self._run(prototype, **variant)

        with tempfile.TemporaryDirectory() as tmp:
            prototype = Path(tmp) / "round-1.html"
            prototype.write_text("reviewed", encoding="utf-8")
            self._run(prototype)
            prototype.write_text("changed bytes", encoding="utf-8")
            with self.assertRaisesRegex(TransactionConflict, "use next round"):
                self._run(prototype)

        with tempfile.TemporaryDirectory() as tmp:
            prototype = Path(tmp) / "round-1.html"
            prototype.write_text("reviewed", encoding="utf-8")
            (Path(tmp) / "confirm-round-1.json").write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(TransactionConflict, "legacy confirm"):
                self._run(prototype)

    def test_malformed_decision_metadata_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            prototype = Path(tmp) / "round-1.html"
            prototype.write_text("reviewed", encoding="utf-8")
            (Path(tmp) / "decision-round-1.json").write_text(
                "{not json", encoding="utf-8"
            )
            with self.assertRaisesRegex(TransactionConflict, "metadata is unreadable"):
                self._run(prototype)

    def test_projection_failures_repair_from_committed_entry(self) -> None:
        for failed_name in ("confirm-round-1.json", "log.md"):
            with self.subTest(failed_name=failed_name), tempfile.TemporaryDirectory() as tmp:
                prototype = Path(tmp) / "round-1.html"
                prototype.write_text("reviewed", encoding="utf-8")
                calls = 0

                def collect(*args: object) -> dict:
                    nonlocal calls
                    calls += 1
                    return {
                        "choice": "确认通过", "feedback": "清晰",
                        "anchors": [], "aborted": False,
                    }

                real_write = transaction._atomic_write
                failed = False

                def flaky_write(path: Path, content: str) -> None:
                    nonlocal failed
                    if path.name == failed_name and not failed:
                        failed = True
                        raise OSError(f"injected {failed_name} failure")
                    real_write(path, content)

                with mock.patch.object(transaction, "_atomic_write", side_effect=flaky_write):
                    with self.assertRaises(OSError):
                        self._run(prototype, collect=collect)
                result = self._run(prototype, collect=collect)
                self.assertEqual(calls, 1)
                self.assertTrue(Path(result["confirm_record_path"]).is_file())
                self.assertTrue((Path(tmp) / "log.md").is_file())

    def test_decision_entry_failure_leaves_no_recoverable_authority(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            prototype = Path(tmp) / "round-1.html"
            prototype.write_text("reviewed", encoding="utf-8")
            real_write = transaction._atomic_write

            def fail_entry(path: Path, content: str) -> None:
                if path.name == "decision-round-1.json":
                    raise OSError("injected entry failure")
                real_write(path, content)

            with mock.patch.object(transaction, "_atomic_write", side_effect=fail_entry):
                with self.assertRaises(OSError):
                    self._run(prototype)
            self.assertFalse((Path(tmp) / "decision-round-1.json").exists())
            self.assertFalse((Path(tmp) / "confirm-round-1.json").exists())
            self.assertFalse((Path(tmp) / "log.md").exists())

    def _run(
        self, prototype: Path, *, summary: str = "summary",
        report_ref: str = "report.md", options: list[str] | None = None,
        collect=None,
    ) -> dict:
        if collect is None:
            collect = lambda *args: {
                "choice": "确认通过", "feedback": "清晰",
                "anchors": [], "aborted": False,
            }
        return run_preview_transaction(
            path_arg=str(prototype), html=None, summary=summary, round_n=1,
            report_ref=report_ref,
            options=options or ["确认通过", "需要修改"], collect=collect,
        )

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
