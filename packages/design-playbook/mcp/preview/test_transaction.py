#!/usr/bin/env python3
"""Contract tests for the Preview decision transaction."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

# One import seam (ADR-0022): package root on sys.path once, then absolute
# design_playbook.* imports below. No per-runtime sys.path adapters.
_PKG_ROOT = Path(__file__).resolve().parents[2]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))
from design_playbook.mcp.preview import transaction  # noqa: E402
from design_playbook.mcp.preview import versions  # noqa: E402
from design_playbook.mcp.preview.integrity import prototype_html_digest  # noqa: E402
from design_playbook.mcp.preview.transaction import (  # noqa: E402
    PreviewTransactionError,
    TransactionConflict,
    run_preview_transaction,
)


def _static_collect(choice: str, feedback: str):
    def collect(
        prototype: Path,
        summary: str,
        options: list[str],
        round_n: int,
        *,
        criteria: list[dict[str, str]],
    ) -> dict:
        return {
            "choice": choice,
            "feedback": feedback,
            "anchors": [],
            "aborted": False,
        }
    return collect


class PreviewDecisionTransactionTests(unittest.TestCase):
    def test_path_mode_persists_replayable_prototype_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            prototype = Path(tmp) / "round-1.html"
            prototype.write_text("<html>path mode</html>", encoding="utf-8")

            run_preview_transaction(
                path_arg=str(prototype), html=None, summary="summary", round_n=1,
                report_ref="report.md", options=["确认通过", "需要修改"],
                collect=_static_collect("确认通过", "清晰"),
            )

            entry = json.loads(
                (Path(tmp) / "decision-round-1.json").read_text(encoding="utf-8"))
            self.assertEqual(entry["prototype_mode"], "path")
            self.assertEqual(entry["prototype_path"], str(prototype))
            replay = versions.state_at(Path(tmp), 1)
            self.assertIsNone(replay["prototype_html"])
            self.assertEqual(replay["prototype_path"], str(prototype))
            with self.assertRaisesRegex(versions.VersionError, "path-mode"):
                versions.fork(
                    Path(tmp), branch="alt", from_round=1,
                    new_dir=Path(tmp) / "fork-alt",
                    report_ref="alt.md", summary="alternate",
                )

    def test_path_mode_requires_nonempty_prototype_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            prototype = Path(tmp) / "prototype.html"
            prototype.write_text("<html>path mode</html>", encoding="utf-8")
            self._run(prototype)
            entry_path = Path(tmp) / "decision-round-1.json"
            entry = json.loads(entry_path.read_text(encoding="utf-8"))
            entry["prototype_path"] = " "
            entry_path.write_text(transaction.json_text(entry), encoding="utf-8")

            with self.assertRaisesRegex(TransactionConflict, "metadata is invalid"):
                self._run(prototype)

    def test_confirm_pass_commits_confirm_and_audit_artifacts(self) -> None:
        seen: list[tuple[Path, str, list[str], int]] = []

        def collect(
            prototype: Path,
            summary: str,
            options: list[str],
            round_n: int,
            *,
            criteria: list[dict[str, str]],
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
                "skipped": False,
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

    def test_skip_is_explicit_non_confirm_and_never_satisfies_floor(self) -> None:
        # ADR-0008 amendment: skip is an explicit exempt pass - never a
        # confirm, floor not evaluated, no confirm record, never satisfies G5.
        result, confirm, log = self._run_submission(
            {"choice": "跳过", "feedback": "", "anchors": [], "aborted": False}
        )

        self.assertFalse(result["confirmed"])
        self.assertTrue(result["floor_pass"])
        self.assertTrue(result["skipped"])
        self.assertEqual(result["selected_options"], ["跳过"])
        self.assertIsNone(confirm)
        self.assertIn("- selected: 跳过", log)

    def test_bare_english_skip_label_is_also_recognised(self) -> None:
        result, confirm, _ = self._run_submission(
            {"choice": "skip", "feedback": "", "anchors": [], "aborted": False}
        )

        self.assertFalse(result["confirmed"])
        self.assertTrue(result["skipped"])
        self.assertIsNone(confirm)

    def test_pass_stays_a_confirm_label_not_a_skip(self) -> None:
        # "pass" historically confirms; it must not be reclassified as skip.
        result, confirm, _ = self._run_submission(
            {"choice": "pass", "feedback": "间距合理", "anchors": [], "aborted": False}
        )

        self.assertTrue(result["confirmed"])
        self.assertFalse(result["skipped"])
        self.assertTrue(confirm is not None and confirm["confirmed"])

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

            def collect(*args: object, criteria: list[dict[str, str]]) -> dict:
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

    def test_same_binding_retry_preserves_invalid_confirm(self) -> None:
        cases = {
            "malformed": "{",
            "non-object": "[]",
            "legacy": None,
            "other-decision": {"decision_id": "other"},
            "tampered": {"feedback": "tampered"},
        }
        for label, mutation in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                prototype = Path(tmp) / "round-1.html"
                prototype.write_text("reviewed", encoding="utf-8")
                self._run(prototype)
                preview_dir = Path(tmp)
                entry = transaction.load_entry(
                    preview_dir / "decision-round-1.json")
                self.assertIsNotNone(entry)
                expected = transaction._confirm_record(entry)
                if label == "legacy":
                    del expected["decision_id"]
                    invalid_text = transaction.json_text(expected)
                elif isinstance(mutation, dict):
                    invalid_text = transaction.json_text({**expected, **mutation})
                else:
                    invalid_text = mutation
                confirm_path = preview_dir / "confirm-round-1.json"
                confirm_path.write_text(invalid_text, encoding="utf-8")

                with self.assertRaises(TransactionConflict):
                    self._run(prototype)

                self.assertEqual(
                    confirm_path.read_text(encoding="utf-8"), invalid_text)

    def test_unconfirmed_retry_preserves_unexpected_confirm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            prototype = Path(tmp) / "round-1.html"
            prototype.write_text("reviewed", encoding="utf-8")
            collect = _static_collect("需要修改", "adjust spacing")

            self._run(prototype, collect=collect)
            confirm_path = Path(tmp) / "confirm-round-1.json"
            invalid_text = "{"
            confirm_path.write_text(invalid_text, encoding="utf-8")

            with self.assertRaises(TransactionConflict):
                self._run(prototype, collect=collect)

            self.assertEqual(
                confirm_path.read_text(encoding="utf-8"), invalid_text)

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

                def collect(*args: object, criteria: list[dict[str, str]]) -> dict:
                    nonlocal calls
                    calls += 1
                    return {
                        "choice": "确认通过", "feedback": "清晰",
                        "anchors": [], "aborted": False,
                    }

                real_write = transaction.atomic_write
                failed = False

                def flaky_write(path: Path, content: str) -> None:
                    nonlocal failed
                    if path.name == failed_name and not failed:
                        failed = True
                        raise OSError(f"injected {failed_name} failure")
                    real_write(path, content)

                with mock.patch.object(transaction, "atomic_write", side_effect=flaky_write):
                    with self.assertRaises(PreviewTransactionError) as caught:
                        self._run(prototype, collect=collect)
                self.assertTrue(caught.exception.details["retryable"])
                self.assertEqual(
                    Path(caught.exception.details["artifact"]).name, failed_name
                )
                result = self._run(prototype, collect=collect)
                self.assertEqual(calls, 1)
                self.assertTrue(Path(result["confirm_record_path"]).is_file())
                self.assertTrue((Path(tmp) / "log.md").is_file())

    def test_active_round_lock_fails_fast_without_second_collector(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            prototype = Path(tmp) / "round-1.html"
            prototype.write_text("reviewed", encoding="utf-8")
            entered = threading.Event()
            release = threading.Event()
            first_error: list[BaseException] = []

            def blocking_collect(
                *args: object, criteria: list[dict[str, str]]
            ) -> dict:
                entered.set()
                release.wait(3)
                return {
                    "choice": "需要修改", "feedback": "调整",
                    "anchors": [], "aborted": False,
                }

            def run_first() -> None:
                try:
                    self._run(prototype, collect=blocking_collect)
                except BaseException as exc:
                    first_error.append(exc)

            thread = threading.Thread(target=run_first)
            thread.start()
            self.assertTrue(entered.wait(2))
            second_calls = 0

            def second_collect(
                *args: object, criteria: list[dict[str, str]]
            ) -> dict:
                nonlocal second_calls
                second_calls += 1
                return {}

            with self.assertRaises(PreviewTransactionError) as caught:
                self._run(prototype, collect=second_collect)
            self.assertTrue(caught.exception.details["retryable"])
            self.assertEqual(second_calls, 0)
            release.set()
            thread.join(3)
            self.assertFalse(thread.is_alive())
            self.assertEqual(first_error, [])
            self.assertFalse((Path(tmp) / "decision-round-1.lock").exists())

    def test_active_transaction_refreshes_heartbeat(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            prototype = Path(tmp) / "round-1.html"
            prototype.write_text("reviewed", encoding="utf-8")
            entered = threading.Event()
            release = threading.Event()
            errors: list[BaseException] = []

            def collect(*args: object, criteria: list[dict[str, str]]) -> dict:
                entered.set()
                release.wait(2)
                return {
                    "choice": "需要修改", "feedback": "调整",
                    "anchors": [], "aborted": False,
                }

            def run() -> None:
                try:
                    self._run(prototype, collect=collect)
                except BaseException as exc:
                    errors.append(exc)

            with mock.patch.object(transaction, "LOCK_HEARTBEAT_SECONDS", 0.02):
                thread = threading.Thread(target=run)
                thread.start()
                self.assertTrue(entered.wait(1))
                lock = Path(tmp) / "decision-round-1.lock"
                initial = lock.stat().st_mtime_ns
                deadline = time.time() + 1
                while lock.stat().st_mtime_ns == initial and time.time() < deadline:
                    time.sleep(0.01)
                self.assertGreater(lock.stat().st_mtime_ns, initial)
                release.set()
                thread.join(2)

            self.assertEqual(errors, [])
            self.assertFalse(lock.exists())

    def test_old_owner_cannot_delete_replacement_directory_lease(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            preview_dir = Path(tmp)
            lock_name = ".lease.lock"
            lock_path = preview_dir / lock_name
            guard_path = lock_path.with_suffix(lock_path.suffix + ".recovery")
            old_lease = transaction.directory_lock(
                preview_dir, lock_name, timeout_seconds=1,
                stale_seconds=1, heartbeat_seconds=10, poll_seconds=0.001,
            )
            old_lease.__enter__()

            owner_checked = threading.Event()
            allow_old_release = threading.Event()
            replacement_entered = threading.Event()
            release_replacement = threading.Event()
            old_errors: list[BaseException] = []
            replacement_errors: list[BaseException] = []
            real_lock_owner = transaction._lock_owner

            def pause_old_owner_check(path: Path) -> str:
                owner = real_lock_owner(path)
                if threading.current_thread().name == "old-release":
                    owner_checked.set()
                    if not allow_old_release.wait(timeout=2):
                        raise TimeoutError("old release was not resumed")
                return owner

            def release_old() -> None:
                try:
                    old_lease.__exit__(None, None, None)
                except BaseException as exc:
                    old_errors.append(exc)

            def hold_replacement() -> None:
                try:
                    with transaction.directory_lock(
                        preview_dir, lock_name, timeout_seconds=1,
                        stale_seconds=1, heartbeat_seconds=10,
                        poll_seconds=0.001,
                    ):
                        replacement_entered.set()
                        release_replacement.wait(timeout=2)
                except BaseException as exc:
                    replacement_errors.append(exc)

            with mock.patch.object(
                transaction, "_lock_owner", side_effect=pause_old_owner_check,
            ):
                old_thread = threading.Thread(
                    target=release_old, name="old-release")
                old_thread.start()
                self.assertTrue(owner_checked.wait(timeout=1))

                replacement_thread = threading.Thread(target=hold_replacement)
                stale_time = time.time() - 2
                os.utime(lock_path, (stale_time, stale_time))
                os.utime(guard_path, (stale_time, stale_time))
                replacement_thread.start()
                replacement_entered.wait(timeout=0.1)
                allow_old_release.set()
                self.assertTrue(replacement_entered.wait(timeout=1))
                old_thread.join(timeout=1)
                lock_survived_old_release = lock_path.is_file()
                release_replacement.set()
                replacement_thread.join(timeout=1)

            self.assertFalse(old_thread.is_alive())
            self.assertFalse(replacement_thread.is_alive())
            self.assertEqual(old_errors, [])
            self.assertEqual(replacement_errors, [])
            self.assertTrue(lock_survived_old_release)

    def test_directory_lease_reports_ownership_loss(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            preview_dir = Path(tmp)
            lock_name = ".lease.lock"
            lock_path = preview_dir / lock_name

            with self.assertRaisesRegex(
                transaction.DirectoryLockError, "ownership lost",
            ):
                with transaction.directory_lock(
                    preview_dir, lock_name, timeout_seconds=1,
                    stale_seconds=1, heartbeat_seconds=10,
                    poll_seconds=0.001,
                ):
                    lock_path.write_text("replacement-owner", encoding="utf-8")

            self.assertEqual(
                lock_path.read_text(encoding="utf-8"), "replacement-owner")

    def test_active_directory_lease_cannot_be_reclaimed_after_stale_gap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            preview_dir = Path(tmp)
            lock_name = ".lease.lock"
            lock_path = preview_dir / lock_name
            active_lease = transaction.directory_lock(
                preview_dir, lock_name, timeout_seconds=1,
                stale_seconds=0.05, heartbeat_seconds=10,
                poll_seconds=0.001,
            )
            active_lease.__enter__()
            stale_time = time.time() - 1
            os.utime(lock_path, (stale_time, stale_time))

            replacement_entered = threading.Event()
            release_replacement = threading.Event()
            replacement_errors: list[BaseException] = []
            active_errors: list[BaseException] = []

            def hold_replacement() -> None:
                try:
                    with transaction.directory_lock(
                        preview_dir, lock_name, timeout_seconds=1,
                        stale_seconds=0.05, heartbeat_seconds=10,
                        poll_seconds=0.001,
                    ):
                        replacement_entered.set()
                        release_replacement.wait(timeout=2)
                except BaseException as exc:
                    replacement_errors.append(exc)

            replacement_thread = threading.Thread(target=hold_replacement)
            replacement_thread.start()
            entered_while_active = replacement_entered.wait(timeout=0.1)
            if entered_while_active:
                release_replacement.set()
                replacement_thread.join(timeout=1)
            try:
                active_lease.__exit__(None, None, None)
            except BaseException as exc:
                active_errors.append(exc)
            self.assertTrue(replacement_entered.wait(timeout=1))
            release_replacement.set()
            replacement_thread.join(timeout=1)

            self.assertFalse(entered_while_active)
            self.assertEqual(active_errors, [])
            self.assertEqual(replacement_errors, [])
            self.assertFalse(replacement_thread.is_alive())

    def test_stale_lock_requires_matching_binding(self) -> None:
        for binding_matches in (True, False):
            with self.subTest(binding_matches=binding_matches), tempfile.TemporaryDirectory() as tmp:
                prototype = Path(tmp) / "round-1.html"
                prototype.write_text("reviewed", encoding="utf-8")
                digest = transaction.compute_binding_digest(
                    round_n=1,
                    prototype_html_hash=prototype_html_digest(
                        prototype.read_bytes()
                    ),
                    report_ref="report.md", summary="summary",
                    options=["确认通过", "需要修改"],
                )["digest"]
                lock = Path(tmp) / "decision-round-1.lock"
                lock.write_text(
                    json.dumps({
                        "owner_id": "dead", "decision_id": "prior",
                        "binding_digest": digest if binding_matches else "different",
                    }),
                    encoding="utf-8",
                )
                stale = time.time() - transaction.LOCK_STALE_SECONDS - 1
                import os
                os.utime(lock, (stale, stale))
                if binding_matches:
                    result = self._run(prototype)
                    self.assertTrue(result["decision_id"])
                    self.assertFalse(lock.exists())
                    self.assertFalse(
                        lock.with_suffix(lock.suffix + ".recovery").exists()
                    )
                else:
                    with self.assertRaises(TransactionConflict) as caught:
                        self._run(prototype)
                    self.assertFalse(caught.exception.details["retryable"])

    def test_collector_failure_cleans_lock(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            prototype = Path(tmp) / "round-1.html"
            prototype.write_text("reviewed", encoding="utf-8")

            def fail_collect(
                *args: object, criteria: list[dict[str, str]]
            ) -> dict:
                raise RuntimeError("browser closed")

            with self.assertRaisesRegex(RuntimeError, "browser closed"):
                self._run(prototype, collect=fail_collect)
            self.assertFalse((Path(tmp) / "decision-round-1.lock").exists())

    def test_decision_entry_failure_leaves_no_recoverable_authority(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            prototype = Path(tmp) / "round-1.html"
            prototype.write_text("reviewed", encoding="utf-8")
            real_write = transaction.atomic_write

            def fail_entry(path: Path, content: str) -> None:
                if path.name == "decision-round-1.json":
                    raise OSError("injected entry failure")
                real_write(path, content)

            with mock.patch.object(transaction, "atomic_write", side_effect=fail_entry):
                with self.assertRaises(PreviewTransactionError) as caught:
                    self._run(prototype)
            self.assertTrue(caught.exception.details["retryable"])
            self.assertEqual(
                Path(caught.exception.details["artifact"]).name,
                "decision-round-1.json",
            )
            self.assertFalse((Path(tmp) / "decision-round-1.json").exists())
            self.assertFalse((Path(tmp) / "confirm-round-1.json").exists())
            self.assertFalse((Path(tmp) / "log.md").exists())

    def test_confirm_record_includes_spec_criteria_review(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prototype = root / "round-1.html"
            report = root / "report.md"
            spec = root / "spec.md"
            prototype.write_text("<html><body>reviewed</body></html>", encoding="utf-8")
            report.write_text("# Decision report\n", encoding="utf-8")
            spec.write_text(
                """# Spec

## L1 Goal
- Outcome summary: Review a queue monitor UI.
## L2 Structure
Page.
## L3 Flow
Flow.
## L4 Details
Details.
## L5 Edges
Edges.
## L6 Acceptance
1. Queue cards: Given jobs exist, When the monitor renders, Then active and queued counts are visible.
2. Failure affordance: Given failed jobs exist, When a reviewer scans the table, Then retry guidance is visible.
""",
                encoding="utf-8",
            )

            def collect(
                prototype: Path,
                summary: str,
                options: list[str],
                round_n: int,
                *,
                criteria: list[dict[str, str]],
            ) -> dict:
                self.assertEqual(
                    [item["id"] for item in criteria], ["L6.1", "L6.2"]
                )
                return {
                    "choice": "确认通过",
                    "feedback": "checked criteria",
                    "anchors": [],
                    "aborted": False,
                    "criteria_review": [
                        {"id": "L6.2", "title": "tampered", "checked": True}
                    ],
                }

            result = run_preview_transaction(
                path_arg=str(prototype),
                html=None,
                summary="summary",
                round_n=1,
                report_ref=str(report),
                options=["确认通过", "需要修改"],
                collect=collect,
            )
            entry = json.loads((root / "decision-round-1.json").read_text(
                encoding="utf-8"))
            confirm = json.loads((root / "confirm-round-1.json").read_text(
                encoding="utf-8"))

        expected = [
            {"id": "L6.1", "title": "Queue cards", "checked": False},
            {"id": "L6.2", "title": "Failure affordance", "checked": True},
        ]
        self.assertEqual(result["criteria_review"], expected)
        self.assertEqual(entry["outcome"]["criteria_review"], expected)
        self.assertEqual(confirm["criteria_review"], expected)

    def _run(
        self, prototype: Path, *, summary: str = "summary",
        report_ref: str = "report.md", options: list[str] | None = None,
        collect=None,
    ) -> dict:
        if collect is None:
            collect = _static_collect("确认通过", "清晰")
        return run_preview_transaction(
            path_arg=str(prototype), html=None, summary=summary, round_n=1,
            report_ref=report_ref,
            options=options or ["确认通过", "需要修改"], collect=collect,
        )

    def _run_submission(
        self, submission: dict
    ) -> tuple[dict, dict | None, str]:
        def collect(
            prototype: Path,
            summary: str,
            options: list[str],
            round_n: int,
            *,
            criteria: list[dict[str, str]],
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
