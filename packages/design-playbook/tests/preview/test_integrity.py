#!/usr/bin/env python3
"""Contract tests for package-internal Preview integrity interface."""
from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# One import seam (ADR-0022): package root on sys.path once, then absolute
# design_playbook.* imports below. No per-runtime sys.path adapters.
_PKG_ROOT = Path(__file__).resolve().parents[2]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from design_playbook.mcp.preview import ledger  # noqa: E402
from design_playbook.mcp.preview.integrity import (  # noqa: E402
    evaluate_feedback_floor,
    inspect_preview,
    prototype_html_digest,
)


class PreviewIntegrityDigestTests(unittest.TestCase):
    def test_digest_normalizes_line_endings(self) -> None:
        expected = "93c17f46a1252c82f9a9a78f3d3753a77a97ff8af6a7833ddb437ce6ce313370"
        for raw in (b"<div>a\nb</div>", b"<div>a\r\nb</div>", b"<div>a\rb</div>"):
            with self.subTest(raw=raw):
                self.assertEqual(prototype_html_digest(raw), expected)
    def test_digest_known_outputs_cover_text_and_utf8(self) -> None:
        cases = {
            b"": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            b"<html></html>": "b633a587c652d02386c4f16f8c6f6aab7352d97f16367c3c40576214372dd628",
            "太挤了".encode("utf-8"): "1729a1292ae2927c5d18a180512a57a6e93e361f69abd2b7a52ab78947f7b716",
            "安师大".encode("utf-8"): "8188b9130fcc89d3aa974d4a719fa90d62113bfd3a7c3ca124f51a69ae575a98",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(prototype_html_digest(raw), expected)


class PreviewIntegrityFloorTests(unittest.TestCase):
    def test_empty_feedback_and_anchors_fail(self) -> None:
        result = evaluate_feedback_floor("", [])
        self.assertFalse(result.passed)
        self.assertEqual(
            result.reason,
            "confirm with no substantive feedback: empty feedback and no anchor",
        )

    def test_short_cjk_feedback_passes(self) -> None:
        result = evaluate_feedback_floor("太挤了", [])
        self.assertTrue(result.passed)
        self.assertEqual(result.reason, "")

    def test_incomplete_anchor_fails(self) -> None:
        result = evaluate_feedback_floor("", [{"selector": "h2", "comment": ""}])
        self.assertFalse(result.passed)
        self.assertEqual(
            result.reason,
            "anchor missing non-empty selector and comment: "
            "selector='h2' comment=''",
        )

    def test_complete_anchor_passes(self) -> None:
        result = evaluate_feedback_floor(
            "", [{"selector": "h2", "comment": "层级太弱"}]
        )
        self.assertTrue(result.passed)


class PreviewIntegritySnapshotTests(unittest.TestCase):
    def test_snapshot_selects_current_round_and_verifies_prototype(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            preview = Path(tmp)
            (preview / "round-1.html").write_text("old", encoding="utf-8")
            current = b"<html>current</html>"
            (preview / "round-2.html").write_bytes(current)
            (preview / "confirm-round-1.json").write_text(
                json.dumps({"round": 1, "confirmed": True, "floor_pass": True}),
                encoding="utf-8",
            )
            (preview / "confirm-round-2.json").write_text(
                json.dumps(
                    {
                        "round": 2,
                        "confirmed": True,
                        "floor_pass": True,
                        "prototype_html_hash": prototype_html_digest(current),
                        "report_ref": "decision-report.md",
                    }
                ),
                encoding="utf-8",
            )

            snapshot = inspect_preview(preview)

            self.assertTrue(snapshot.occurred)
            self.assertEqual(snapshot.current_round, 2)
            self.assertEqual([record.path.name for record in snapshot.current_confirms], [
                "confirm-round-2.json"
            ])
            self.assertTrue(snapshot.current_confirms[0].valid)
            self.assertEqual(snapshot.current_confirms[0].prototype_status, "match")
            self.assertEqual(snapshot.facts, ())

    def test_snapshot_reports_hash_mismatch_as_host_neutral_fact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            preview = Path(tmp)
            (preview / "round-1.html").write_text("changed", encoding="utf-8")
            (preview / "confirm-round-1.json").write_text(
                json.dumps(
                    {
                        "round": 1,
                        "confirmed": True,
                        "floor_pass": True,
                        "prototype_html_hash": prototype_html_digest(b"original"),
                    }
                ),
                encoding="utf-8",
            )

            snapshot = inspect_preview(preview)

            self.assertEqual(snapshot.current_confirms[0].prototype_status, "mismatch")
            self.assertEqual([fact.code for fact in snapshot.facts], ["hash_mismatch"])
            self.assertNotIn("G5", snapshot.facts[0].detail)

    def test_canonical_confirm_carries_owner_prototype_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            preview = Path(tmp)
            (preview / "round-1.html").write_text("changed", encoding="utf-8")
            (preview / "confirm-round-1.json").write_text(
                json.dumps(
                    {
                        "round": 1,
                        "confirmed": True,
                        "floor_pass": True,
                        "prototype_html_hash": prototype_html_digest(b"original"),
                    }
                ),
                encoding="utf-8",
            )

            snapshot = inspect_preview(preview)

            canonical = snapshot.canonical_current_confirm
            self.assertIsNotNone(canonical)
            # ``valid`` stays flags-only (ADR-0008 confirm/floor flags); the
            # integrity outcome surfaces as the owner-computed prototype
            # status on the same canonical current-round record, so a
            # projection can never upgrade a hash mismatch to confirmed.
            self.assertTrue(canonical.valid)
            self.assertEqual(canonical.prototype_status, "mismatch")
            self.assertEqual(snapshot.current_confirms, (canonical,))

    def test_malformed_confirm_becomes_fact_without_aborting_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            preview = Path(tmp)
            (preview / "log.md").write_text("# log", encoding="utf-8")
            (preview / "confirm-round-1.json").write_text("{", encoding="utf-8")

            snapshot = inspect_preview(preview)

            self.assertTrue(snapshot.occurred)
            self.assertEqual(snapshot.current_confirms, ())
            self.assertEqual(
                [fact.code for fact in snapshot.facts], ["invalid_confirm_record"]
            )

    def test_non_object_confirm_is_fact_and_canonical_status_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            preview = Path(tmp)
            (preview / "round-1.html").write_text("current", encoding="utf-8")
            (preview / "confirm-round-1.json").write_text("[]", encoding="utf-8")

            snapshot = inspect_preview(preview)

            self.assertEqual(
                [fact.code for fact in snapshot.facts], ["confirm_not_object"]
            )
            self.assertIsNotNone(snapshot.canonical_current_confirm)
            self.assertFalse(snapshot.canonical_current_confirm.valid)

    def test_binding_valid_decision_marks_occurrence_without_confirm(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            preview = Path(tmp)
            binding_fields = {
                "round": 3,
                "prototype_html_hash": "a" * 64,
                "report_ref": "decision-report.md",
                "summary": "review",
                "options": ["确认通过", "需要修改"],
            }
            canonical = json.dumps(
                binding_fields,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            binding = {
                **binding_fields,
                "digest": hashlib.sha256(canonical).hexdigest(),
            }
            (preview / "decision-round-3.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "decision_id": "decision-3",
                        "binding": binding,
                        "outcome": {},
                    }
                ),
                encoding="utf-8",
            )

            snapshot = inspect_preview(preview)

            self.assertTrue(snapshot.occurred)
            self.assertEqual(snapshot.occurrence_sources, ("decision-round-3.json",))
            self.assertEqual(snapshot.current_round, 3)
            self.assertEqual(snapshot.current_confirms, ())
            self.assertIsNone(snapshot.canonical_current_confirm)

    def test_malformed_decision_does_not_mark_occurrence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            preview = Path(tmp)
            (preview / "decision-round-1.json").write_text("{}", encoding="utf-8")

            snapshot = inspect_preview(preview)

            self.assertFalse(snapshot.occurred)


class PreviewLedgerGateTests(unittest.TestCase):
    """T-086/DEF-2: run-external ledger union + orphan round INVALID."""

    def test_ledger_orphan_round_is_invalid_not_silent_pass(self) -> None:
        # Simulate the gate-wash attempt: move the round artifacts out of
        # preview/ while the run-external ledger still registers them —
        # G5 must stay INVALID with an observable reason.
        from design_playbook.scripts.g5_preview import check_preview

        with tempfile.TemporaryDirectory() as tmp, \
                tempfile.TemporaryDirectory() as ledger_tmp, \
                mock.patch.dict(
                    os.environ,
                    {ledger.LEDGER_ENV_VAR: ledger_tmp},
                ):
            preview = Path(tmp) / "preview"
            preview.mkdir()
            ledger.append_record(
                preview, {"round": 1, "confirmed": True, "floor_pass": True}
            )

            # Directory empty (records moved away): snapshot says no
            # occurrence, but the ledger still has round 1.
            findings = check_preview(preview, None)

            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].rule_id, "G5.ledger_orphan_round")
            self.assertIn("moved, renamed, or deleted", findings[0].message)

    def test_no_ledger_and_no_artifacts_stays_conditional(self) -> None:
        from design_playbook.scripts.g5_preview import check_preview

        with tempfile.TemporaryDirectory() as tmp, \
                tempfile.TemporaryDirectory() as ledger_tmp, \
                mock.patch.dict(
                    os.environ,
                    {ledger.LEDGER_ENV_VAR: ledger_tmp},
                ):
            preview = Path(tmp) / "preview"
            preview.mkdir()

            findings = check_preview(preview, None)

            self.assertEqual(findings, [])

    def test_transaction_appends_run_external_ledger_record(self) -> None:
        from design_playbook.mcp.preview.transaction import (
            run_preview_transaction,
        )

        def collect(*args: object, criteria: list[dict[str, str]]) -> dict:
            return {
                "choice": "确认通过", "feedback": "清晰",
                "anchors": [], "aborted": False,
            }

        with tempfile.TemporaryDirectory() as tmp, \
                tempfile.TemporaryDirectory() as ledger_tmp, \
                mock.patch.dict(
                    os.environ,
                    {ledger.LEDGER_ENV_VAR: ledger_tmp},
                ):
            prototype = Path(tmp) / "round-1.html"
            prototype.write_text("reviewed", encoding="utf-8")

            run_preview_transaction(
                path_arg=str(prototype), html=None, summary="summary",
                round_n=1, report_ref="report.md",
                options=["确认通过", "需要修改"], collect=collect,
            )

            self.assertEqual(ledger.rounds_for(Path(tmp)), (1,))
            wash_dir = Path(tmp) / "wash"
            wash_dir.mkdir()
            self.assertEqual(ledger.rounds_for(wash_dir), ())


if __name__ == "__main__":
    unittest.main()
