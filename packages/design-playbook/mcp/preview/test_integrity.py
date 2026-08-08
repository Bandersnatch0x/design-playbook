#!/usr/bin/env python3
"""Contract tests for package-internal Preview integrity interface."""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from integrity import (  # noqa: E402
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


if __name__ == "__main__":
    unittest.main()
