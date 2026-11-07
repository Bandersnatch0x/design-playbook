#!/usr/bin/env python3
"""T-152 / T-159: repair proof is derived from the finding, not the annotation.

The unit cases judge ``check_repair_evidence`` over a real temporary run
layout: actual files, actual SHA-256 bytes, and artifact facts collected by
the one G6 owner. The end-to-end cases run the real validator CLI with an
explicit ``--legacy`` selection and are named as structural-only: they prove
the legacy reading, never complete acceptance (the complete subprocess
positive lives in ``test_repair_acceptance.py``).
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
if str(PACKAGE) not in sys.path:
    sys.path.insert(0, str(PACKAGE))

from design_playbook.scripts.g1_spec import ProofRequirement  # noqa: E402
from design_playbook.scripts.g6_records import (  # noqa: E402
    collect_evidence_artifacts,
)
from design_playbook.scripts.repair_evidence import (  # noqa: E402
    check_repair_evidence,
)

FIX = Path(__file__).resolve().parent / "fixtures"
VALIDATOR = PACKAGE / "scripts" / "validate_run.py"

VIEWPORT = {
    "width": 1280, "height": 800,
    "devicePixelRatio": 1.0, "colorScheme": "light",
}
FREEZE = {"enabled": True, "waitFonts": True, "networkIdle": False}
BEFORE_BYTES = b"failure-state-bytes"
AFTER_BYTES = b"repaired-state-bytes"

FINDING = """
issue: empty state primary action is hidden
source: design
fix: show the primary action
severity: S3
disposition: blocking
criteria: L6.3
evidence: evidence/L6.3-empty-r1.png（空态主操作不可见）
"""

LEDGER = """
criterion: L6.3
required: Given empty state When opened Then the primary action is visible
observed: evidence/L6.3-empty-r2.png
result: pass
"""


def _repair_text(*, finding: str = FINDING, annotation: str | None = None,
                 extra_closure: str = "", result: str = "pass") -> str:
    body = annotation if annotation is not None else (
        "  repair-evidence: criterion=L6.3 "
        "before=evidence/L6.3-empty-r1.png "
        "after=evidence/L6.3-empty-r2.png\n")
    ledger = LEDGER.replace("result: pass", f"result: {result}")
    return (
        "# point-back\n\n## Evidence ledger\n"
        + ledger
        + "\n## Findings\n"
        + finding
        + "\n## Verdict\n\n**Recirculate.**\n\n"
        + "- closes: empty state primary action is hidden -> fix -> re-eval -> "
          "0 blocking\n"
        + body
        + extra_closure
    )


REQUIREMENTS = (
    ProofRequirement("L6.3", "known", "screenshot", "empty", (1280, 800)),
)


def _entry(artifact: str, data: bytes, *, criterion: str = "L6.3",
           ts: str = "2026-11-07T10:00:00+08:00",
           declared: str | None = ..., capture_type: str = "screenshot",
           viewport: dict | None = None) -> dict:
    entry = {
        "ts": ts,
        "criterion": criterion,
        "artifact": artifact,
        "request": {
            "schemaVersion": 1,
            "viewport": viewport or dict(VIEWPORT),
            "freeze": dict(FREEZE),
        },
        "capture": {
            "type": capture_type,
            "state": "empty",
            "artifact_path": f"evidence/{artifact}",
        },
    }
    if declared is ...:
        entry["sha256"] = hashlib.sha256(data).hexdigest()
    elif declared is not None:
        entry["sha256"] = declared
    return entry


class _RunLayout:
    """One real temporary run: files, manifest entries, and captured facts."""

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "run"
        self.evidence = self.root / "evidence"
        self.evidence.mkdir(parents=True)
        self.before = self.evidence / "L6.3-empty-r1.png"
        self.after = self.evidence / "L6.3-empty-r2.png"
        self.before.write_bytes(BEFORE_BYTES)
        self.after.write_bytes(AFTER_BYTES)
        self.entries = [
            _entry("L6.3-empty-r1.png", BEFORE_BYTES),
            _entry("L6.3-empty-r2.png", AFTER_BYTES,
                   ts="2026-11-07T11:00:00+08:00"),
        ]

    def write_manifest(self) -> None:
        (self.evidence / "manifest.jsonl").write_text(
            "".join(json.dumps(entry) + "\n" for entry in self.entries),
            encoding="utf-8")

    def facts(self, tokens=None):
        if tokens is None:
            tokens = [f"evidence/{entry['artifact']}"
                      for entry in self.entries
                      if isinstance(entry.get("artifact"), str)]
        return collect_evidence_artifacts(tokens, run_root=self.root)

    def cleanup(self) -> None:
        self._tmp.cleanup()


def _rules(findings) -> set[str]:
    return {item.rule_id for item in findings}


def _check(text: str, layout: _RunLayout, *, complete: bool = True,
           requirements=REQUIREMENTS, extra_entries=()):
    return check_repair_evidence(
        text,
        list(layout.entries) + list(extra_entries),
        requirements=requirements,
        artifact_facts=layout.facts(),
        require_complete=complete,
    )


class CompleteObligationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.layout = _RunLayout()
        self.addCleanup(self.layout.cleanup)

    def test_a_complete_visual_repair_passes(self) -> None:
        self.assertEqual(_check(_repair_text(), self.layout), [])

    def test_omitting_the_annotation_is_blocked(self) -> None:
        text = (
            "# point-back\n\n## Evidence ledger\n" + LEDGER
            + "\n## Findings\n" + FINDING
            + "\n## Verdict\n\n**Recirculate.**\n\n"
            "- closes: empty state primary action is hidden -> fix -> re-eval "
            "-> 0 blocking\n"
        )
        self.assertIn("G4.repair_evidence_missing", _rules(_check(text, self.layout)))

    def test_only_the_repaired_half_is_blocked(self) -> None:
        text = _repair_text(
            annotation="  repair-evidence: criterion=L6.3 "
                       "after=evidence/L6.3-empty-r2.png\n")
        self.assertIn("G4.repair_evidence_unpaired", _rules(_check(text, self.layout)))

    def test_only_the_failing_half_is_blocked(self) -> None:
        text = _repair_text(
            annotation="  repair-evidence: criterion=L6.3 "
                       "before=evidence/L6.3-empty-r1.png\n")
        self.assertIn("G4.repair_evidence_unpaired", _rules(_check(text, self.layout)))

    def test_a_pair_borrowed_from_another_finding_is_blocked(self) -> None:
        other = self.layout.evidence / "other-r1.png"
        other.write_bytes(b"another finding failure")
        self.layout.entries.append(_entry("other-r1.png", b"another finding failure"))
        text = _repair_text().replace("before=evidence/L6.3-empty-r1.png",
                                      "before=evidence/other-r1.png")
        self.assertIn("G4.repair_evidence_before", _rules(_check(text, self.layout)))

    def test_after_must_be_the_current_ledger_observation(self) -> None:
        third = self.layout.evidence / "third.png"
        third.write_bytes(b"third bytes")
        self.layout.entries.append(_entry(
            "third.png", b"third bytes", ts="2026-11-07T12:00:00+08:00"))
        text = _repair_text().replace("after=evidence/L6.3-empty-r2.png",
                                      "after=evidence/third.png")
        self.assertIn("G4.repair_evidence_after", _rules(_check(text, self.layout)))

    def test_a_failing_retest_is_blocked(self) -> None:
        self.assertIn("G4.repair_evidence_result",
                      _rules(_check(_repair_text(result="fail"), self.layout)))

    def test_identical_visual_bytes_are_insufficient_evidence(self) -> None:
        self.layout.after.write_bytes(BEFORE_BYTES)
        self.layout.entries[1] = _entry(
            "L6.3-empty-r2.png", BEFORE_BYTES,
            ts="2026-11-07T11:00:00+08:00")
        self.assertIn("G4.repair_evidence_unchanged",
                      _rules(_check(_repair_text(), self.layout)))

    def test_a_viewport_mismatch_is_blocked(self) -> None:
        self.layout.entries[1] = _entry(
            "L6.3-empty-r2.png", AFTER_BYTES,
            ts="2026-11-07T11:00:00+08:00",
            viewport={**VIEWPORT, "width": 480})
        self.assertIn("G4.repair_evidence_mismatch",
                      _rules(_check(_repair_text(), self.layout)))

    def test_declared_hash_must_match_the_captured_bytes(self) -> None:
        self.layout.entries[1]["sha256"] = "a" * 64
        self.assertIn("G6.artifact_hash_mismatch",
                      _rules(_check(_repair_text(), self.layout)))

    def test_a_required_pair_half_must_declare_a_hash(self) -> None:
        del self.layout.entries[0]["sha256"]
        self.assertIn("G6.artifact_hash_unavailable",
                      _rules(_check(_repair_text(), self.layout)))

    def test_a_removed_artifact_is_blocked_with_the_missing_code(self) -> None:
        self.layout.before.unlink()
        rules = _rules(_check(_repair_text(), self.layout))
        self.assertIn("G6.artifact_missing", rules)
        self.assertNotIn("G4.repair_evidence_unbound", rules)

    def test_a_finding_without_criteria_is_blocked(self) -> None:
        finding = FINDING.replace("criteria: L6.3\n", "")
        self.assertIn("G4.repair_association_missing",
                      _rules(_check(_repair_text(finding=finding), self.layout)))

    def test_an_unnamed_annotation_is_not_guessed_across_criteria(self) -> None:
        finding = FINDING.replace("criteria: L6.3", "criteria: L6.3, L6.4")
        text = _repair_text(finding=finding).replace("criterion=L6.3 ", "")
        requirements = REQUIREMENTS + (
            ProofRequirement("L6.4", "known", "screenshot"),)
        self.assertIn(
            "G4.repair_association_missing",
            _rules(_check(text, self.layout, requirements=requirements)))

    def test_duplicate_criteria_do_not_duplicate_the_obligation(self) -> None:
        finding = FINDING.replace("criteria: L6.3", "criteria: L6.3, L6.3")
        findings = _check(_repair_text(finding=finding), self.layout)
        self.assertIn("G4.repair_association_missing", _rules(findings))
        self.assertNotIn("G4.repair_evidence_missing", _rules(findings))

    def test_a_shared_issue_cannot_be_consumed_by_one_closure(self) -> None:
        second = (
            "\nissue: empty state primary action is hidden\n"
            "source: design\nfix: show the primary action\nseverity: S3\n"
            "disposition: blocking\n")
        text = _repair_text().replace("\n## Verdict", second + "\n## Verdict")
        self.assertIn("G4.repair_association_missing",
                      _rules(_check(text, self.layout)))

    def test_an_unknown_criterion_is_blocked(self) -> None:
        finding = FINDING.replace("criteria: L6.3", "criteria: L6.99")
        self.assertIn("G4.repair_requirement_unavailable",
                      _rules(_check(_repair_text(finding=finding), self.layout)))

    def test_an_unknown_proof_type_is_blocked(self) -> None:
        requirements = (ProofRequirement("L6.3", "unknown"),)
        self.assertIn("G4.repair_requirement_unavailable",
                      _rules(_check(_repair_text(), self.layout,
                                    requirements=requirements)))

    def test_an_annotation_for_another_finding_criterion_is_blocked(self) -> None:
        text = _repair_text().replace("criterion=L6.3", "criterion=L6.4")
        self.assertIn("G4.repair_evidence_unknown_criterion",
                      _rules(_check(text, self.layout)))

    def test_two_annotations_for_one_criterion_are_blocked(self) -> None:
        text = _repair_text(
            extra_closure="  repair-evidence: criterion=L6.3 "
                          "before=evidence/L6.3-empty-r1.png "
                          "after=evidence/L6.3-empty-r2.png\n")
        self.assertIn("G4.repair_evidence_duplicate",
                      _rules(_check(text, self.layout)))

    def test_an_unknown_annotation_key_is_blocked(self) -> None:
        text = _repair_text(
            annotation="  repair-evidence: criterion=L6.3 "
                       "before=evidence/L6.3-empty-r1.png "
                       "after=evidence/L6.3-empty-r2.png note=x\n")
        self.assertIn("G4.repair_evidence_annotation_malformed",
                      _rules(_check(text, self.layout)))

    def test_an_orphan_annotation_is_blocked(self) -> None:
        text = _repair_text(extra_closure=(
            "\n- repair-evidence: criterion=L6.3 "
            "before=evidence/L6.3-empty-r1.png "
            "after=evidence/L6.3-empty-r2.png\n"))
        self.assertIn("G4.repair_evidence_orphan",
                      _rules(_check(text, self.layout)))

    def test_multiple_criteria_must_each_be_settled(self) -> None:
        finding = FINDING.replace("criteria: L6.3", "criteria: L6.3, L6.4")
        extra = self.layout.evidence / "L6.4-r1.png"
        extra.write_bytes(b"second criterion bytes")
        self.layout.entries.append(_entry(
            "L6.4-r1.png", b"second criterion bytes", criterion="L6.4"))
        ledger = LEDGER + (
            "\ncriterion: L6.4\n"
            "required: Given a second state When checked Then it holds\n"
            "observed: evidence/L6.4-r1.png\n"
            "result: pass\n")
        text = _repair_text(finding=finding).replace(LEDGER, ledger)
        requirements = REQUIREMENTS + (
            ProofRequirement("L6.4", "known", "screenshot"),)
        rules = _rules(_check(text, self.layout, requirements=requirements))
        self.assertIn("G4.repair_evidence_missing", rules)

    def test_a_nonvisual_repair_requires_no_screenshot_pair(self) -> None:
        self.layout.entries[1] = _entry(
            "L6.3-empty-r2.png", AFTER_BYTES,
            ts="2026-11-07T11:00:00+08:00",
            capture_type="interaction trace")
        text = (
            "# point-back\n\n## Evidence ledger\n" + LEDGER
            + "\n## Findings\n" + FINDING
            + "\n## Verdict\n\n**Recirculate.**\n\n"
            "- closes: empty state primary action is hidden -> fix -> re-eval "
            "-> 0 blocking\n"
        )
        requirements = (ProofRequirement("L6.3", "known", "interaction_trace"),)
        self.assertEqual(
            _check(text, self.layout, requirements=requirements), [])

    def test_an_automated_check_retest_needs_no_artifact(self) -> None:
        ledger = LEDGER.replace("observed: evidence/L6.3-empty-r2.png",
                                "observed: pytest tests/test_empty.py -q")
        text = _repair_text(annotation="").replace(LEDGER, ledger)
        requirements = (ProofRequirement("L6.3", "known", "automated_check"),)
        self.assertEqual(
            _check(text, self.layout, requirements=requirements), [])

    def test_declaration_coverage_retest_needs_no_capture_request(self) -> None:
        ledger = LEDGER.replace(
            "observed: evidence/L6.3-empty-r2.png",
            "observed: spec L2/L5 declare the empty-state primary action")
        text = _repair_text(annotation="").replace(LEDGER, ledger)
        requirements = (
            ProofRequirement("L6.3", "known", "declaration_coverage"),)
        self.assertEqual(
            _check(text, self.layout, requirements=requirements), [])

    def test_an_orphan_annotation_is_an_error_even_without_a_closed_blocker(
            self) -> None:
        finding = FINDING.replace(
            "disposition: blocking", "disposition: advisory")
        text = _repair_text(finding=finding, extra_closure=(
            "\n- repair-evidence: criterion=L6.3 "
            "before=evidence/L6.3-empty-r1.png "
            "after=evidence/L6.3-empty-r2.png\n"))
        self.assertIn("G4.repair_evidence_orphan",
                      _rules(_check(text, self.layout)))

    def test_a_legal_run_without_a_closed_blocker_adds_nothing(self) -> None:
        text = _repair_text(finding=FINDING.replace(
            "disposition: blocking", "disposition: advisory"))
        self.assertEqual(_check(text, self.layout), [])

    def test_a_snapshot_without_artifact_facts_is_unavailable(self) -> None:
        findings = check_repair_evidence(
            _repair_text(), list(self.layout.entries),
            requirements=REQUIREMENTS, artifact_facts=None,
            require_complete=True)
        self.assertIn("G6.artifact_facts_unavailable", _rules(findings))


class LegacyStructuralTests(unittest.TestCase):
    def setUp(self) -> None:
        self.layout = _RunLayout()
        self.addCleanup(self.layout.cleanup)

    def test_a_legacy_report_without_an_annotation_stays_silent(self) -> None:
        text = _repair_text(annotation="")
        self.assertEqual(_check(text, self.layout, complete=False), [])

    def test_a_legacy_pair_is_validated_through_g6(self) -> None:
        self.layout.entries[1]["sha256"] = "b" * 64
        self.assertIn("G6.artifact_hash_mismatch",
                      _rules(_check(_repair_text(), self.layout, complete=False)))

    def test_a_legacy_leaf_only_half_is_rejected_with_a_migration_code(self) -> None:
        text = _repair_text().replace("before=evidence/L6.3-empty-r1.png",
                                      "before=L6.3-empty-r1.png")
        self.assertIn("G6.reference_prefix",
                      _rules(_check(text, self.layout, complete=False)))

    def test_a_legacy_annotation_without_a_resolvable_criterion_is_rejected(
            self) -> None:
        finding = FINDING.replace("criteria: L6.3\n", "")
        text = _repair_text(finding=finding).replace("criterion=L6.3 ", "")
        self.assertIn("G4.repair_association_missing",
                      _rules(_check(text, self.layout, complete=False)))

    def _make_identical_halves(self) -> None:
        self.layout.after.write_bytes(BEFORE_BYTES)
        self.layout.entries[1] = _entry(
            "L6.3-empty-r2.png", BEFORE_BYTES,
            ts="2026-11-07T11:00:00+08:00")

    def test_a_nonvisual_pair_with_identical_bytes_is_not_rejected(self) -> None:
        # E: the unchanged-bytes rule is a visible-state rule; a declared
        # automated check keeps its explicit pair without a byte-difference
        # obligation.
        self._make_identical_halves()
        requirements = (ProofRequirement("L6.3", "known", "automated_check"),)
        self.assertEqual(
            _check(_repair_text(), self.layout, complete=False,
                   requirements=requirements), [])

    def test_a_visual_pair_with_identical_bytes_is_still_rejected(self) -> None:
        self._make_identical_halves()
        self.assertIn(
            "G4.repair_evidence_unchanged",
            _rules(_check(_repair_text(), self.layout, complete=False)))

    def test_a_single_finding_criterion_is_inherited(self) -> None:
        text = _repair_text().replace("criterion=L6.3 ", "")
        self.assertEqual(_check(text, self.layout, complete=False), [])


class LegacyStructuralCliTests(unittest.TestCase):
    """Explicit --legacy only: this is not complete-acceptance evidence."""

    def _run_dir(self, annotation: str, *, declare_hash: bool = True) -> Path:
        tmp = Path(tempfile.mkdtemp(prefix="t159-legacy-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        shutil.copy(FIX / "pass" / "spec.md", tmp / "spec.md")
        pointback = (FIX / "pass" / "point-back.md").read_text(encoding="utf-8")
        pointback = pointback.replace(
            "- closes: batch retry has no confirm step -> reopen `domain` -> "
            "fix: confirm Dialog + consequence -> re-eval: confirm present "
            "before execute -> **0 blocking**",
            "- closes: batch retry has no confirm step -> fix -> re-eval -> "
            "0 blocking\n" + annotation,
        )
        (tmp / "point-back.md").write_text(pointback, encoding="utf-8")
        evidence = tmp / "evidence"
        evidence.mkdir()
        before = evidence / "L6.1-r1.png"
        after = evidence / "L6.1-r2.png"
        before.write_bytes(BEFORE_BYTES)
        after.write_bytes(AFTER_BYTES)
        entries = [
            _entry("L6.1-r1.png", BEFORE_BYTES, criterion="L6.1"),
            _entry("L6.1-r2.png", AFTER_BYTES, criterion="L6.1",
                   ts="2026-11-07T11:00:00+08:00"),
        ]
        if not declare_hash:
            for entry in entries:
                del entry["sha256"]
        (evidence / "manifest.jsonl").write_text(
            "".join(json.dumps(entry) + "\n" for entry in entries),
            encoding="utf-8")
        return tmp

    def _validate(self, run_dir: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(VALIDATOR), str(run_dir / "spec.md"),
             str(run_dir / "point-back.md"), "--legacy",
             "--evidence-dir", str(run_dir / "evidence"),
             "--run-root", str(run_dir)],
            capture_output=True, text=True, encoding="utf-8",
        )

    def test_the_repaired_half_alone_fails_in_the_legacy_reading(self) -> None:
        run_dir = self._run_dir(
            "  repair-evidence: criterion=L6.1 after=evidence/L6.1-r2.png\n")
        result = self._validate(run_dir)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("G4 repair-evidence", result.stdout)
        self.assertNotIn("RUN OK", result.stdout)

    def test_a_valid_pair_leaves_the_legacy_structure_green(self) -> None:
        run_dir = self._run_dir(
            "  repair-evidence: criterion=L6.1 "
            "before=evidence/L6.1-r1.png after=evidence/L6.1-r2.png\n")
        result = self._validate(run_dir)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("RUN OK", result.stdout)


class ParseFactTests(unittest.TestCase):
    def test_the_closure_trail_owns_the_annotation_fact(self) -> None:
        from design_playbook.scripts.finding_syntax import parse_closures

        facts = parse_closures(_repair_text())
        self.assertEqual(len(facts.closures), 1)
        self.assertEqual(len(facts.closures[0].annotations), 1)
        self.assertEqual(facts.orphan_annotations, ())


if __name__ == "__main__":
    unittest.main()