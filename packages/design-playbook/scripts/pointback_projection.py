"""Immutable Point-back owner projection for Run Snapshot consumers."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum
from typing import Literal, cast

from design_playbook.mcp.evidence.ledger_syntax import parse_ledger
from design_playbook.scripts.audit_preferences import parse_audit_marker
from design_playbook.scripts.finding_syntax import (
    VALID_DISPOSITIONS,
    parse_findings,
    severity_axis,
)
from design_playbook.scripts.g2_g4_pointback import _check_pointback_facts
from design_playbook.scripts.g11_coverage import check_coverage
from design_playbook.scripts.g6_records import ledger_observed
from design_playbook.scripts.verdict_syntax import parse_verdict

CriterionOutcome = Literal["pass", "fail", "blocked", "notApplicable"]
FindingDisposition = Literal["blocking", "advisory", "info"]
FindingOwnerKind = Literal["declaration", "artifact", "decision", "unknown"]
FindingAvailability = Literal["unknown"]
FindingNonKnownReason = Literal["finding-disposition-missing"]

_NON_CANONICAL_VERDICT_RULES = frozenset({
    "G3.missing_verdict",
    "G3.repeated_verdict",
    "G3.verdict_count",
})


class PointBackProjectionError(ValueError):
    """A fixed, path-free reason the owner cannot project complete facts."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class VerdictDisposition(str, Enum):
    """Canonical Point-back verdict disposition, including non-known states."""

    PASS = "Pass"
    RECIRCULATE = "Recirculate"
    UNAUDITED = "unaudited"
    NO_CANONICAL_VALUE = "noCanonicalValue"


@dataclass(frozen=True)
class FindingOwner:
    """Owner explicitly declared by a Point-back finding."""

    kind: FindingOwnerKind
    domain_id: str | None
    source_ref: str | None


@dataclass(frozen=True)
class DomainFinding:
    """One validated evaluator finding in owner order."""

    finding_id: str
    criterion_ids: tuple[str, ...]
    issue: str
    severity: str
    disposition: FindingDisposition
    owner: FindingOwner
    repair: str


@dataclass(frozen=True)
class NonKnownFinding:
    """Stable Finding identity whose full domain value is not owner-known."""

    finding_id: str
    availability: FindingAvailability
    reason: FindingNonKnownReason


@dataclass(frozen=True)
class CriterionEvaluation:
    """One owner-ordered criterion evaluation from the Evidence ledger.

    ``artifact_token`` is only the existing G6 ledger token. It is an
    unbound Artifact candidate, never an Evidence binding.
    """

    criterion_id: str
    outcome: CriterionOutcome
    required_proof: str
    observed_summary: str
    artifact_token: str | None


@dataclass(frozen=True)
class EvaluationCoverage:
    """Ledger coverage counts over the declared criterion set."""

    declared: int
    reviewed: int
    unreviewed: int
    complete: bool


@dataclass(frozen=True)
class PointBackProjection:
    """Complete immutable semantic read result owned by Point-back."""

    verdict: VerdictDisposition
    criteria: tuple[CriterionEvaluation, ...]
    findings: tuple[DomainFinding | NonKnownFinding, ...]
    coverage: EvaluationCoverage


def _normalise_identity_part(value: str) -> str:
    return " ".join(value.casefold().split())


def _finding_id(source: str, issue: str) -> str:
    identity = "\0".join((
        "pointback-finding-v1",
        _normalise_identity_part(source),
        _normalise_identity_part(issue),
    ))
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return f"finding-{digest}"


def _validate_criterion_ids(criterion_ids: tuple[str, ...]) -> None:
    expected = tuple(f"L6.{number}" for number in range(1, len(criterion_ids) + 1))
    if not criterion_ids or criterion_ids != expected:
        raise PointBackProjectionError("criterion-ids-invalid")


def _validate_owner_policy(diagnostics: list[object]) -> None:
    rule_ids = tuple(getattr(item, "rule_id") for item in diagnostics)
    effective = tuple(
        rule_id for rule_id in rule_ids
        if rule_id not in _NON_CANONICAL_VERDICT_RULES
    )
    if not effective:
        return
    if any(
        rule_id.startswith("G2.") and "finding" not in rule_id
        or rule_id == "G3.pass_requires_result"
        for rule_id in effective
    ):
        raise PointBackProjectionError("ledger-malformed")
    if any(
        rule_id.startswith("G2.finding")
        or rule_id.startswith("G2.s3")
        or rule_id.startswith("G4.")
        or rule_id == "G3.no_findings_without_pass"
        for rule_id in effective
    ):
        raise PointBackProjectionError("finding-malformed")
    raise PointBackProjectionError("pointback-malformed")


def project_pointback(
    text: str,
    criterion_ids: tuple[str, ...],
) -> PointBackProjection:
    """Project canonical Point-back facts without exposing parser internals."""
    _validate_criterion_ids(criterion_ids)
    marker = parse_audit_marker(text)
    verdict_facts = parse_verdict(text)
    ledger_facts = parse_ledger(text)
    pointback_findings = parse_findings(text)

    if marker.present and marker.audited is None:
        raise PointBackProjectionError("audit-marker-ambiguous")

    diagnostics = _check_pointback_facts(
        text,
        len(criterion_ids),
        pointback_findings,
        ledger_facts=ledger_facts,
        verdict_facts=verdict_facts,
    )
    _validate_owner_policy(diagnostics)
    if check_coverage(text):
        raise PointBackProjectionError("coverage-malformed")

    if marker.present and marker.audited is False:
        verdict = VerdictDisposition.UNAUDITED
    elif verdict_facts.canonical == "pass":
        verdict = VerdictDisposition.PASS
    elif verdict_facts.canonical == "recirculate":
        verdict = VerdictDisposition.RECIRCULATE
    else:
        verdict = VerdictDisposition.NO_CANONICAL_VALUE

    rows_by_criterion = {
        row.values("criterion")[0]: row
        for row in ledger_facts.rows
        if row.values("criterion")
    }
    observed_by_criterion = dict(ledger_observed(text, ledger_facts))
    criteria = []
    for criterion_id in criterion_ids:
        row = rows_by_criterion[criterion_id]
        raw_result = row.values("result")[0].casefold()
        outcome = cast(
            CriterionOutcome,
            "notApplicable" if raw_result == "n/a" else raw_result,
        )
        token = observed_by_criterion.get(criterion_id, "")
        if not token.startswith("evidence/"):
            token = None
        criteria.append(CriterionEvaluation(
            criterion_id=criterion_id,
            outcome=outcome,
            required_proof=row.values("required")[0],
            observed_summary=row.values("observed")[0],
            artifact_token=token,
        ))

    findings = []
    finding_ids: set[str] = set()
    for fields in pointback_findings:
        source = fields["source"][0]
        finding_id = _finding_id(source, fields["issue"][0])
        if finding_id in finding_ids:
            raise PointBackProjectionError("finding-duplicate")
        finding_ids.add(finding_id)
        dispositions = fields["disposition"]
        if not dispositions:
            findings.append(NonKnownFinding(
                finding_id=finding_id,
                availability="unknown",
                reason="finding-disposition-missing",
            ))
            continue
        if len(dispositions) != 1:
            raise PointBackProjectionError("finding-disposition-invalid")
        disposition = dispositions[0].casefold()
        if disposition not in VALID_DISPOSITIONS:
            raise PointBackProjectionError("finding-disposition-invalid")
        severity = severity_axis(fields["severity"][0])
        if severity is None:
            raise PointBackProjectionError("finding-severity-invalid")
        criterion_refs = tuple(
            criterion_id for criterion_id in criterion_ids
            if criterion_id == source
        )
        findings.append(DomainFinding(
            finding_id=finding_id,
            criterion_ids=criterion_refs,
            issue=fields["issue"][0],
            severity=severity,
            disposition=cast(FindingDisposition, disposition),
            owner=FindingOwner(
                kind="declaration",
                domain_id=source,
                source_ref=None,
            ),
            repair=fields["fix"][0],
        ))

    declared = len(criterion_ids)
    audited = marker.audited is not False
    reviewed = len(criteria) if audited else 0
    return PointBackProjection(
        verdict=verdict,
        criteria=tuple(criteria),
        findings=tuple(findings),
        coverage=EvaluationCoverage(
            declared=declared,
            reviewed=reviewed,
            unreviewed=declared - reviewed,
            complete=audited and reviewed == declared,
        ),
    )
