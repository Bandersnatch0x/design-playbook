#!/usr/bin/env python3
"""G6 binding regressions: latest-instant selection and contract diagnostics."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

PACKAGE = Path(__file__).resolve().parents[1]
if str(PACKAGE) not in sys.path:
    sys.path.insert(0, str(PACKAGE))

from design_playbook.mcp.evidence.capture_contract import CaptureFact  # noqa: E402
from design_playbook.scripts import g6_evidence  # noqa: E402
from design_playbook.scripts.g6_evidence import (  # noqa: E402
    EvidenceReference,
    reference_finding,
    select_bound_entry,
    validate_references,
)
from design_playbook.scripts.g6_records import EvidenceArtifactFact  # noqa: E402

# 10:00Z is the later capture; its string sorts below the older +08:00 stamp.
LATER = "2026-09-24T10:00:00Z"
EARLIER = "2026-09-24T12:00:00+08:00"
SAME_INSTANT = "2026-09-24T18:00:00+08:00"


def _entry(ts: object, digest: str = "d") -> dict:
    return {"criterion": "L6.1", "artifact": "a.png", "ts": ts, "sha256": digest}


class LatestBindingInstantTests(unittest.TestCase):
    def test_mixed_offsets_pick_the_later_instant(self) -> None:
        entries = [_entry(EARLIER, "older"), _entry(LATER, "newer")]
        self.assertEqual(
            select_bound_entry(entries, "L6.1", "a.png")["sha256"], "newer")

    def test_unknown_pair_has_no_binding(self) -> None:
        self.assertIsNone(select_bound_entry([_entry(LATER)], "L6.2", "a.png"))

    def test_two_entries_at_one_instant_stay_ambiguous(self) -> None:
        entries = [_entry(LATER, "first"), _entry(SAME_INSTANT, "tie")]
        with self.assertRaises(ValueError) as caught:
            select_bound_entry(entries, "L6.1", "a.png")
        self.assertEqual(str(caught.exception), "conflicting-bindings")

    def test_repeated_identical_entry_is_not_a_conflict(self) -> None:
        entry = _entry(LATER)
        self.assertEqual(select_bound_entry([entry, dict(entry)], "L6.1", "a.png"), entry)

    def test_unusable_timestamps_fail_closed(self) -> None:
        for ts in ("2026-09-24T23:00:00", "2026-09-24 10:00", "", None, 1_758_000_000):
            with self.subTest(ts=ts):
                with self.assertRaises(ValueError) as caught:
                    select_bound_entry([_entry(EARLIER), _entry(ts)], "L6.1", "a.png")
                self.assertEqual(str(caught.exception), "invalid-binding-timestamp")


class CaptureContractDiagnosticTests(unittest.TestCase):
    """F4: every capture-contract fact stays a named G6 failure."""

    def _binding(self, request: dict):
        entry = {
            "criterion": "L6.1", "artifact": "a.png", "ts": LATER,
            "sha256": "a" * 64, "request": request,
        }
        fact = EvidenceArtifactFact(
            reference="evidence/a.png", artifact="a.png",
            sha256="a" * 64, size=1)
        return validate_references(
            [EvidenceReference("L6.1", "evidence/a.png")],
            [entry], {"L6.1"}, (fact,))[0]

    def _request(self, **extra) -> dict:
        return {
            "schemaVersion": 1,
            "viewport": {
                "width": 1280, "height": 800,
                "devicePixelRatio": 1.0, "colorScheme": "light",
            },
            "freeze": {"enabled": True, "waitFonts": True,
                       "networkIdle": False},
            **extra,
        }

    def test_a_malformed_design_binding_is_a_named_g6_failure(self) -> None:
        binding = self._binding(self._request(design={"fontSizes": 42}))
        self.assertEqual(
            binding.diagnostics[0].code, "capture_design_shape")
        projected = reference_finding(binding, binding.diagnostics[0])
        self.assertEqual(projected.rule_id, "G6.capture_design_shape")

    def test_an_unmapped_contract_fact_never_reads_as_valid(self) -> None:
        with mock.patch.object(
            g6_evidence, "validate_capture_snapshot",
            return_value=[CaptureFact("future_shape", "unknown shape", "x", "y")],
        ):
            binding = self._binding(self._request())
        self.assertEqual(binding.diagnostics[0].code, "capture_contract")
        projected = reference_finding(binding, binding.diagnostics[0])
        self.assertEqual(projected.rule_id, "G6.capture_contract")
        self.assertIn("future_shape", projected.message)


if __name__ == "__main__":
    unittest.main()
