#!/usr/bin/env python3
"""Skeleton point-back and audit-marker tests (issue #67, spec #65, ADR-0033).

Split from tests/test_audit_preferences.py (file-size budget): this module
owns the anti-forgery half - skeleton generation, marker fact parsing, and
the closed loop validate_run / run_status projection. The preference
parsing/merge/write-back halves live in test_audit_preferences.py and
test_audit_writeback.py.

Acceptance coverage (issue #67):
* skeleton point-back satisfies the point-back gate parsers by
  construction (lockstep test pins template vs parsers);
* parse_audit_marker reports marker facts without policy;
* closed-loop anti-forgery round trip: skeleton generated -> marker
  parsed as unaudited -> non-strict validate passes / --strict and the
  --require-* flags reject -> run_status projects "not audited".
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "packages" / "design-playbook"

if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))

from design_playbook.scripts import audit_preferences  # noqa: E402

# Gate parsers the skeleton must satisfy by construction (issue #67): the
# module imports these rather than duplicating regexes, and the lockstep
# test below pins the template against the very same parsers.
from design_playbook.mcp.evidence.ledger_syntax import parse_ledger  # noqa: E402
from design_playbook.scripts.g1_spec import _l6_items  # noqa: E402
from design_playbook.scripts.g11_coverage import check_coverage  # noqa: E402
from design_playbook.scripts.g2_g4_pointback import (  # noqa: E402
    _findings as pointback_findings,
    check_pointback,
)
from design_playbook.scripts.verdict_syntax import parse_verdict  # noqa: E402

VALIDATOR = PKG / "scripts" / "validate_run.py"
RUN_STATUS = PKG / "scripts" / "run_status.py"


# Minimal G1-valid spec used by the skeleton tests: three L6 criteria, so
# the skeleton ledger must carry exactly three n/a rows.
SKELETON_SPEC = """# Spec - skeleton probe page

## L1 定位与意图

- Probe spec for the skeleton anti-forgery tests.

## L2 信息架构

- One list.

## L3 核心链路

- open -> reviewed

## L4 组件功能细节

- Row details.

## L5 边界条件

- Empty state shows a placeholder.

## L6 验收标准

- Given the probe list, When it opens, Then rows are visible.
- Given a row, When it is expanded, Then details are visible.
- Given no rows, When it opens, Then an empty state is visible.
"""


# The AUDIT.unaudited finding's stable message prefix - the text
# projection prints the message body (rule_id stays in the JSON face).
AUDIT_DIAGNOSTIC = "AUDIT: point-back carries 'audited: false'"


def _validate(spec: Path, pointback: Path, *extra: str):
    return subprocess.run(
        [sys.executable, str(VALIDATOR), str(spec), str(pointback), *extra],
        capture_output=True, text=True, check=False,
            encoding="utf-8", errors="replace",
    )


def _run_status_json(run_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(RUN_STATUS), str(run_root), "--json"],
        capture_output=True, text=True, check=False,
            encoding="utf-8", errors="replace",
    )


class SkeletonLockstepTests(unittest.TestCase):
    """Issue #67 acceptance 2: the skeleton satisfies the point-back gate
    parsers by construction - one lockstep test pins the template against
    the parsers the module imports (never duplicated regexes)."""

    def test_lockstep_template_vs_gate_parsers(self) -> None:
        skeleton = audit_preferences.skeleton_pointback(SKELETON_SPEC)
        n = len(_l6_items(SKELETON_SPEC))
        self.assertEqual(n, 3)
        # G2/G3/G4 accept the skeleton wholesale.
        self.assertEqual(check_pointback(skeleton, n), [])
        # Verdict facts: exactly one anchored heading, exactly one value,
        # canonical Recirculate (never a forged Pass).
        facts = parse_verdict(skeleton)
        self.assertEqual(facts.heading_count, 1)
        self.assertEqual(facts.value_count, 1)
        self.assertEqual(facts.canonical, "recirculate")
        # G11 (existence): the limitation sentence opts the skeleton into
        # the six-block shape; the coverage statement satisfies it.
        self.assertIn("## Limitations statement", skeleton)
        self.assertEqual(check_coverage(skeleton), [])
        self.assertEqual(check_coverage(skeleton, required=True), [])
        # Ledger shape: one n/a row per L6 criterion, no evidence/ binding.
        rows = parse_ledger(skeleton).rows
        self.assertEqual(len(rows), n)
        for index, row in enumerate(rows, 1):
            self.assertEqual(row.values("criterion"), (f"L6.{index}",))
            self.assertEqual(row.values("result"), ("n/a",))
            self.assertFalse(row.raw_observed.startswith("evidence/"))
        # One S0/info finding keeps G3.no_findings_without_pass silent.
        findings = pointback_findings(skeleton)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], ["S0"])
        self.assertEqual(findings[0]["disposition"], ["info"])
        # Fixed limitation sentence and marker are part of the template.
        self.assertIn(audit_preferences.SKELETON_LIMITATION_SENTENCE, skeleton)
        self.assertIn("audited: false", skeleton)

    def test_skeleton_generation_is_deterministic(self) -> None:
        self.assertEqual(
            audit_preferences.skeleton_pointback(SKELETON_SPEC),
            audit_preferences.skeleton_pointback(SKELETON_SPEC),
        )

    def test_skeleton_rejects_spec_without_criteria(self) -> None:
        with self.assertRaises(ValueError):
            audit_preferences.skeleton_pointback(
                "# Spec\n\n## L6 验收标准\n\nNo list items here.\n")


class AuditMarkerTests(unittest.TestCase):
    """Issue #67: parse_audit_marker reports facts only - no policy, the
    same creed as verdict_syntax's "parse, no policy"."""

    def test_absent_marker_reports_no_opinion(self) -> None:
        marker = audit_preferences.parse_audit_marker("# Report\n\nClean.\n")
        self.assertFalse(marker.present)
        self.assertIsNone(marker.audited)
        self.assertEqual(marker.marker_count, 0)

    def test_unaudited_marker_parses_false(self) -> None:
        marker = audit_preferences.parse_audit_marker(
            "# Report\n\naudited: false\n\nBody.\n")
        self.assertTrue(marker.present)
        self.assertIs(marker.audited, False)
        self.assertEqual(marker.marker_count, 1)

    def test_audited_marker_parses_true(self) -> None:
        marker = audit_preferences.parse_audit_marker("audited: true\n")
        self.assertTrue(marker.present)
        self.assertIs(marker.audited, True)

    def test_marker_value_is_case_insensitive(self) -> None:
        marker = audit_preferences.parse_audit_marker("audited: FALSE\n")
        self.assertIs(marker.audited, False)

    def test_repeated_marker_is_ambiguous_facts_only(self) -> None:
        marker = audit_preferences.parse_audit_marker(
            "audited: false\n\naudited: false\n")
        self.assertTrue(marker.present)
        self.assertIsNone(marker.audited)
        self.assertEqual(marker.marker_count, 2)

    def test_malformed_marker_candidate_is_present_but_ambiguous(self) -> None:
        for text in (
            "audited: false for now\n",
            " audited: false\n",
            "audited: false # forged comment\n",
        ):
            with self.subTest(text=text):
                marker = audit_preferences.parse_audit_marker(text)
                self.assertTrue(marker.present)
                self.assertIsNone(marker.audited)
                self.assertEqual(marker.marker_count, 1)

    def test_skeleton_round_trips_through_the_marker_parser(self) -> None:
        skeleton = audit_preferences.skeleton_pointback(SKELETON_SPEC)
        marker = audit_preferences.parse_audit_marker(skeleton)
        self.assertTrue(marker.present)
        self.assertIs(marker.audited, False)


class ClosedLoopAntiForgeryTests(unittest.TestCase):
    """Issue #67 acceptance 1 + spec #65 centerpiece: skeleton generated ->
    marker parsed as unaudited -> non-strict validate passes / --strict and
    the --require-* flags reject -> run_status projects "not audited".
    Only the single deep module makes this round trip testable."""

    def _skeleton_pair(self, tmp: Path) -> tuple[Path, Path]:
        spec_path = tmp / "spec.md"
        pointback_path = tmp / "point-back.md"
        spec_path.write_text(SKELETON_SPEC, encoding="utf-8")
        pointback_path.write_text(
            audit_preferences.skeleton_pointback(SKELETON_SPEC),
            encoding="utf-8",
        )
        return spec_path, pointback_path

    def test_non_strict_validation_passes_the_skeleton(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            spec, pointback = self._skeleton_pair(Path(tmp))
            result = _validate(spec, pointback)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("RUN OK", result.stdout)

    def test_strict_rejects_the_skeleton_with_audit_finding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            spec, pointback = self._skeleton_pair(Path(tmp))
            result = _validate(spec, pointback, "--strict")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(AUDIT_DIAGNOSTIC, result.stdout)

    def test_require_evidence_rejects_the_skeleton(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            spec, pointback = self._skeleton_pair(Path(tmp))
            result = _validate(spec, pointback, "--require-evidence")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(AUDIT_DIAGNOSTIC, result.stdout)

    def test_require_coverage_rejects_the_skeleton(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            spec, pointback = self._skeleton_pair(Path(tmp))
            result = _validate(spec, pointback, "--require-coverage")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn(AUDIT_DIAGNOSTIC, result.stdout)

    def test_require_preview_alone_does_not_reject_the_skeleton(self) -> None:
        # Preview may legitimately precede the audit; ADR-0033 D12 names
        # only --strict / --require-evidence / --require-coverage for the
        # AUDIT rejection. Without preview artifacts the run still fails
        # G5.require_preview - but never via the AUDIT finding.
        with tempfile.TemporaryDirectory() as tmp:
            spec, pointback = self._skeleton_pair(Path(tmp))
            result = _validate(spec, pointback, "--require-preview")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("require-preview", result.stdout)
        self.assertNotIn(AUDIT_DIAGNOSTIC, result.stdout)

    def test_strict_rejection_names_the_audit_finding_rule_id(self) -> None:
        # The JSON projection carries the stable AUDIT.* rule ID (no new
        # G gate number) alongside the message.
        with tempfile.TemporaryDirectory() as tmp:
            spec, pointback = self._skeleton_pair(Path(tmp))
            result = _validate(spec, pointback, "--require-coverage",
                               "--format", "json")
        self.assertEqual(result.returncode, 1, result.stdout)
        rule_ids = {entry["rule_id"] for entry in json.loads(result.stdout)}
        self.assertIn("AUDIT.unaudited", rule_ids)

    def test_strict_rejects_duplicate_marker_forgery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            spec, pointback = self._skeleton_pair(Path(tmp))
            pointback.write_text(
                pointback.read_text(encoding="utf-8") + "\naudited: true\n",
                encoding="utf-8",
            )
            result = _validate(spec, pointback, "--require-coverage")
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertIn("ambiguous or malformed 'audited:' marker", result.stdout)

    def test_strict_rejects_indented_or_commented_marker(self) -> None:
        for replacement in (
            " audited: false",
            "audited: false # hidden from exact parser",
        ):
            with self.subTest(replacement=replacement), tempfile.TemporaryDirectory() as tmp:
                spec, pointback = self._skeleton_pair(Path(tmp))
                text = pointback.read_text(encoding="utf-8").replace(
                    "audited: false", replacement, 1)
                pointback.write_text(text, encoding="utf-8")
                result = _validate(spec, pointback, "--require-coverage")
            self.assertEqual(result.returncode, 1, result.stdout)
            self.assertIn("ambiguous or malformed 'audited:' marker", result.stdout)

    def test_run_status_suppresses_ambiguous_marker_verdict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp)
            (run_root / "spec.md").write_text(SKELETON_SPEC, encoding="utf-8")
            pointback = audit_preferences.skeleton_pointback(SKELETON_SPEC)
            (run_root / "point-back.md").write_text(
                pointback + "\naudited: true\n", encoding="utf-8")
            result = _run_status_json(run_root)
        payload = json.loads(result.stdout)
        self.assertIs(payload["audited"], False)
        self.assertEqual(payload["audit_marker_state"], "ambiguous")
        self.assertIsNone(payload["verdict"])
        self.assertIn("duplicate or malformed", payload["next"])

    def test_deleted_marker_cannot_hide_a_skeleton(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            spec_path = tmp / "spec.md"
            pointback_path = tmp / "point-back.md"
            spec_path.write_text(SKELETON_SPEC, encoding="utf-8")
            skeleton = audit_preferences.skeleton_pointback(SKELETON_SPEC)
            pointback_path.write_text(
                skeleton.replace("audited: false\n\n", "", 1),
                encoding="utf-8",
            )
            strict = _validate(spec_path, pointback_path, "--require-coverage")
            status = _run_status_json(Path(tmp))
        self.assertEqual(strict.returncode, 1, strict.stdout)
        self.assertIn("ambiguous or malformed 'audited:' marker", strict.stdout)
        payload = json.loads(status.stdout)
        self.assertIs(payload["audited"], False)
        self.assertEqual(payload["audit_marker_state"], "ambiguous")
        self.assertIsNone(payload["verdict"])

    def test_run_status_projects_not_audited(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp)
            (run_root / "spec.md").write_text(SKELETON_SPEC, encoding="utf-8")
            (run_root / "point-back.md").write_text(
                audit_preferences.skeleton_pointback(SKELETON_SPEC),
                encoding="utf-8",
            )
            result = _run_status_json(run_root)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertIs(payload["audited"], False)
        self.assertIsNone(payload["verdict"])
        self.assertNotIn("confirm ## Verdict", payload["next"])
        self.assertIn("not audited", payload["next"].casefold())

    def test_run_status_keeps_verdict_projection_for_real_reports(self) -> None:
        # Regression guard: the unaudited projection must not leak into
        # marker-less point-backs (the legacy majority).
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp)
            (run_root / "spec.md").write_text("spec\n", encoding="utf-8")
            (run_root / "point-back.md").write_text(
                "## Verdict\n\n**Pass.**\n", encoding="utf-8")
            result = _run_status_json(run_root)
        payload = json.loads(result.stdout)
        self.assertIsNone(payload["audited"])
        self.assertEqual(payload["verdict"], "Pass")


if __name__ == "__main__":
    unittest.main()
