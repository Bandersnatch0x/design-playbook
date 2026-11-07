#!/usr/bin/env python3
"""G6 binding regressions: latest-instant selection and contract diagnostics."""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

PACKAGE = Path(__file__).resolve().parents[1]
if str(PACKAGE) not in sys.path:
    sys.path.insert(0, str(PACKAGE))

from design_playbook.mcp.evidence import containment  # noqa: E402
from design_playbook.mcp.evidence.capture_contract import CaptureFact  # noqa: E402
from design_playbook.scripts import g6_evidence, g6_records  # noqa: E402
from design_playbook.scripts.g6_evidence import (  # noqa: E402
    EvidenceReference,
    check_evidence,
    reference_finding,
    select_bound_entry,
    validate_references,
)
from design_playbook.scripts.g6_records import (  # noqa: E402
    EvidenceArtifactFact,
    collect_evidence_artifacts,
)
from design_playbook.scripts.run_facts import capture_run_facts  # noqa: E402

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


class ExplicitEvidenceRootTests(unittest.TestCase):
    """S4: the manifest root and the file root cannot be combined.

    The compatibility I/O seam must use the same explicit-authority decision
    as the capture path: on a split or unavailable root it reports a named
    unavailable finding instead of an empty success or a foreign read.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="t159-explicit-roots-")
        self.addCleanup(self._tmp.cleanup)
        self.first = Path(self._tmp.name) / "first"
        self.second = Path(self._tmp.name) / "second"
        for run in (self.first, self.second):
            (run / "evidence").mkdir(parents=True)
        self.first_file = self.first / "evidence" / "proof.png"
        self.second_file = self.second / "evidence" / "proof.png"
        self.first_file.write_bytes(b"first bytes")
        self.second_file.write_bytes(b"second bytes")
        self.request = {
            "schemaVersion": 1,
            "viewport": {"width": 1280, "height": 800,
                         "devicePixelRatio": 1, "colorScheme": "light"},
            "freeze": {"enabled": True, "waitFonts": True,
                       "networkIdle": False},
        }
        self.entry = {
            "criterion": "L6.1", "artifact": "proof.png",
            "ts": "2026-11-08T00:00:00Z", "request": dict(self.request),
            "sha256": hashlib.sha256(self.second_file.read_bytes()).hexdigest(),
        }
        (self.first / "evidence" / "manifest.jsonl").write_text(
            json.dumps(self.entry) + "\n", encoding="utf-8")
        self.observed = [("L6.1", "evidence/proof.png")]

    def _check(self, evidence_dir, run_root) -> set[str]:
        return {
            finding.rule_id for finding in check_evidence(
                "", 1, evidence_dir, run_root, observed_rows=self.observed)
        }

    def _restore_first_bytes(self) -> None:
        self.first_file.write_bytes(self.second_file.read_bytes())

    def test_matching_roots_report_the_real_manifest_mismatch(self) -> None:
        self.assertEqual(
            self._check(self.first / "evidence", self.first),
            {"G6.artifact_hash_mismatch"})

    def test_a_split_root_is_a_named_unavailable_error(self) -> None:
        self.assertEqual(
            self._check(self.first / "evidence", self.second),
            {"G6.artifact_facts_unavailable"})

    def test_restoring_the_bytes_makes_both_valid_authorities_pass(self) -> None:
        self._restore_first_bytes()
        self.assertEqual(
            self._check(self.first / "evidence", self.first), set())
        self.assertEqual(
            self._check(self.first / "evidence", None), set())

    def test_a_split_root_cannot_open_the_foreign_artifact(self) -> None:
        def forbidden(*_args, **_kwargs):
            raise AssertionError("a split root opened an artifact")

        with mock.patch.object(g6_records, "_open_binary", forbidden), \
                mock.patch.object(containment, "read_artifact", forbidden):
            rules = self._check(self.first / "evidence", self.second)
        self.assertEqual(rules, {"G6.artifact_facts_unavailable"})

    def test_supplied_frozen_facts_are_never_reopened(self) -> None:
        self._restore_first_bytes()
        facts = collect_evidence_artifacts(
            ["evidence/proof.png"], run_root=self.first)

        def forbidden(*_args, **_kwargs):
            raise AssertionError("supplied facts triggered a read")

        with mock.patch.object(g6_records, "_open_binary", forbidden), \
                mock.patch.object(containment, "read_artifact", forbidden):
            rules = {
                finding.rule_id for finding in check_evidence(
                    "", 1, self.first / "evidence", self.second,
                    observed_rows=self.observed, entries=[self.entry],
                    artifact_facts=facts)
            }
        self.assertEqual(rules, set())

    def test_capture_rejects_the_same_split_root(self) -> None:
        facts = capture_run_facts(
            run_root=self.second, evidence_dir=self.first / "evidence")
        self.assertIsNone(facts.evidence_artifacts)


if __name__ == "__main__":
    unittest.main()
