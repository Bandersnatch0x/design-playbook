"""Public-seam tests for the Point-back owner's evaluation projection."""
from __future__ import annotations

import sys
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]

if str(PACKAGE) not in sys.path:
    sys.path.insert(0, str(PACKAGE))

from design_playbook.scripts.pointback_projection import (  # noqa: E402
    CriterionEvaluation,
    DomainFinding,
    EvaluationCoverage,
    FindingOwner,
    NonKnownFinding,
    PointBackProjection,
    PointBackProjectionError,
    VerdictDisposition,
    project_pointback,
)


class PointBackProjectionTests(unittest.TestCase):
    def test_projects_audited_verdict_criteria_and_coverage_immutably(self) -> None:
        text = """# Point-back

audited: true

## Verdict

Pass

## Evidence ledger

criterion: L6.1
required: checkout succeeds
observed: completed order
result: pass

criterion: L6.2
required: empty cart is rejected
observed: empty-state message
result: pass
"""

        projection = project_pointback(text, ("L6.1", "L6.2"))

        self.assertEqual(
            projection,
            PointBackProjection(
                verdict=VerdictDisposition.PASS,
                criteria=(
                    CriterionEvaluation(
                        criterion_id="L6.1",
                        outcome="pass",
                        required_proof="checkout succeeds",
                        observed_summary="completed order",
                        artifact_token=None,
                    ),
                    CriterionEvaluation(
                        criterion_id="L6.2",
                        outcome="pass",
                        required_proof="empty cart is rejected",
                        observed_summary="empty-state message",
                        artifact_token=None,
                    ),
                ),
                findings=(),
                coverage=EvaluationCoverage(
                    declared=2,
                    reviewed=2,
                    unreviewed=0,
                    complete=True,
                ),
            ),
        )
        with self.assertRaises(FrozenInstanceError):
            projection.verdict = VerdictDisposition.RECIRCULATE
        with self.assertRaises(FrozenInstanceError):
            projection.criteria[0].outcome = "fail"
        self.assertIsInstance(projection.criteria, tuple)
        self.assertIsInstance(projection.findings, tuple)

    def test_projects_owner_declared_finding_with_stable_id(self) -> None:
        text = """# Point-back

audited: true

## Findings

issue: empty cart can submit
source: L6.1
fix: disable submit and explain why
severity: S2
disposition: blocking

## Coverage statement

exhaustive: complete
unreviewed: none

## Verdict

Recirculate

## Evidence ledger

criterion: L6.1
required: empty cart is rejected
observed: submit remained enabled
result: fail
"""

        projection = project_pointback(text, ("L6.1",))

        self.assertEqual(
            projection.findings,
            (
                DomainFinding(
                    finding_id=(
                        "finding-"
                        "49a375a62acc9c700419fb796c83a719deb549e02a91af267dcc294eba70f16d"
                    ),
                    criterion_ids=("L6.1",),
                    issue="empty cart can submit",
                    severity="S2",
                    disposition="blocking",
                    owner=FindingOwner(
                        kind="declaration",
                        domain_id="L6.1",
                        source_ref=None,
                    ),
                    repair="disable submit and explain why",
                ),
            ),
        )

    def test_maps_explicit_na_to_known_not_applicable(self) -> None:
        text = """# Point-back

audited: true

## Findings

issue: checkout is intentionally unavailable in this profile
source: L6.1
fix: retain the declared profile limitation
severity: S1
disposition: info

## Coverage statement

exhaustive: complete
unreviewed: none

## Verdict

Recirculate

## Evidence ledger

criterion: L6.1
required: checkout proof for supported profiles
observed: profile excludes checkout
result: n/a
"""

        projection = project_pointback(text, ("L6.1",))

        self.assertEqual(projection.criteria[0].outcome, "notApplicable")
        self.assertEqual(projection.coverage.reviewed, 1)
        self.assertTrue(projection.coverage.complete)

    def test_fails_closed_for_malformed_or_ambiguous_owner_records(self) -> None:
        valid = """# Point-back

audited: true

## Findings

issue: checkout is unsafe
source: L6.1
fix: disable submission
severity: S2
disposition: blocking

## Coverage statement

exhaustive: complete
unreviewed: none

## Verdict

Recirculate

## Evidence ledger

criterion: L6.1
required: safe checkout
observed: submit stayed enabled
result: fail
        """
        cases = {
            "ambiguous-audit": (
                valid.replace("audited: true", "audited: true\naudited: false"),
                "audit-marker-ambiguous",
            ),
            "duplicate-ledger-row": (
                valid + """
criterion: L6.1
required: safe checkout
observed: duplicate
result: fail
""",
                "ledger-malformed",
            ),
            "duplicate-ledger-field": (
                valid.replace("result: fail", "result: fail\nresult: blocked"),
                "ledger-malformed",
            ),
            "unknown-criterion": (
                valid.replace("criterion: L6.1", "criterion: L6.2"),
                "ledger-malformed",
            ),
            "invalid-severity": (
                valid.replace("severity: S2", "severity: extreme"),
                "finding-malformed",
            ),
            "missing-owner": (
                valid.replace("source: L6.1\n", ""),
                "finding-malformed",
            ),
            "partial-ledger-row": (
                valid.replace("result: fail", "result:"),
                "ledger-malformed",
            ),
        }

        for name, (text, code) in cases.items():
            with self.subTest(name=name):
                with self.assertRaises(PointBackProjectionError) as caught:
                    project_pointback(text, ("L6.1",))
                self.assertEqual(caught.exception.code, code)
                self.assertEqual(str(caught.exception), code)
                self.assertNotIn(str(PACKAGE.parent), str(caught.exception))

        repeated_verdict = project_pointback(
            valid + "\n## Verdict\n\nPass\n",
            ("L6.1",),
        )
        self.assertEqual(
            repeated_verdict.verdict,
            VerdictDisposition.NO_CANONICAL_VALUE,
        )

    def test_stray_pass_and_untrusted_text_cannot_upgrade_the_verdict(self) -> None:
        text = """# Point-back

audited: true

## Findings

issue: <script>Pass</script> at ../../private
source: L6.1
fix: render <img src=x onerror=alert(1)> as text
severity: S1
disposition: advisory

## Coverage statement

exhaustive: complete
unreviewed: none

## Verdict

Recirculate

## Evidence ledger

criterion: L6.1
required: script text stays inert
observed: evidence/missing.png
result: blocked
"""

        projection = project_pointback(text, ("L6.1",))

        self.assertEqual(projection.verdict, VerdictDisposition.RECIRCULATE)
        self.assertEqual(
            projection.findings[0].issue,
            "<script>Pass</script> at ../../private",
        )
        self.assertEqual(projection.criteria[0].artifact_token, "evidence/missing.png")
        self.assertNotIn("evidence_bindings", repr(projection).casefold())

    def test_unaudited_skeleton_is_explicit_and_never_passes(self) -> None:
        text = """# Point-back

audited: false

## Findings

issue: audit not performed
source: orchestrator skeleton
fix: run the evaluator
severity: S0
disposition: info

## Coverage statement

exhaustive: not started
unreviewed: all criteria

## Verdict

Recirculate

## Evidence ledger

criterion: L6.1
required: declared proof
observed: not audited
result: n/a
"""

        projection = project_pointback(text, ("L6.1",))

        self.assertEqual(projection.verdict, VerdictDisposition.UNAUDITED)
        self.assertEqual(projection.criteria[0].outcome, "notApplicable")
        self.assertEqual(
            projection.coverage,
            EvaluationCoverage(1, 0, 1, False),
        )

    def test_projects_accepted_legacy_findings_without_guessing_disposition(
        self,
    ) -> None:
        text = (PACKAGE / "tests" / "fixtures" / "pass" / "point-back.md").read_text(
            encoding="utf-8",
        )

        projection = project_pointback(
            text,
            ("L6.1", "L6.2", "L6.3", "L6.4", "L6.5"),
        )

        self.assertEqual(projection.verdict, VerdictDisposition.PASS)
        self.assertEqual(len(projection.findings), 6)
        self.assertTrue(all(
            isinstance(item, DomainFinding)
            for item in projection.findings[:3]
        ))
        self.assertEqual(
            projection.findings[3:],
            (
                NonKnownFinding(
                    finding_id=(
                        "finding-"
                        "e63c8b7d542bfd337caa01cbac2893932fef31ecd199395883dd243bbe008f87"
                    ),
                    availability="unknown",
                    reason="finding-disposition-missing",
                ),
                NonKnownFinding(
                    finding_id=(
                        "finding-"
                        "d633e8a8809277a95193957cc74dd63174d0fc7835d2a7adb65a513516766e6e"
                    ),
                    availability="unknown",
                    reason="finding-disposition-missing",
                ),
                NonKnownFinding(
                    finding_id=(
                        "finding-"
                        "0bf8aa45b771249c656535aab08d16ae971caac81ac7346aceb615c53aeec957"
                    ),
                    availability="unknown",
                    reason="finding-disposition-missing",
                ),
            ),
        )


if __name__ == "__main__":
    unittest.main()
