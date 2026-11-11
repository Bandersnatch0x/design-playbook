"""G4 repair-evidence obligations (T-152 / T-159 / research seam I8).

A repaired blocker used to close on a sentence: the closure trail said
"fix -> re-eval -> 0 blocking" and nothing required the artifacts behind it.
T-152 made a declared pair countable; T-159 closes the remaining hole by
deriving the obligation from the finding instead of from the annotation that
happens to be present.

The finding owns the association (``criteria:``), the closure owns the repair
annotation, and the ledger owns the retest result:

```text
id: F-1
issue: empty state primary action is hidden
criteria: L6.3
evidence: evidence/L6.3-empty-r1.png

- closes: F-1 -> fix -> re-eval -> 0 blocking
  repair-evidence: criterion=L6.3 before=evidence/L6.3-empty-r1.png after=evidence/L6.3-empty-r2.png
```

Complete acceptance (CLI bare / ``--strict``) derives one obligation per
declared criterion of every blocking finding a single closure claims to have
closed. Missing association, unknown proof type, unknown criterion, orphan or
duplicated annotation, missing half, and a pair borrowed from another closure
all fail closed. Duplicate explicit annotations for one closure x criterion are
a structural error in every mode; the unchanged-bytes rule applies to declared
visible-state proofs only, so a declared automated check or trace keeps an
identical pair. ``--legacy`` and explicit ``--require-*`` selections keep the
structural reading: an annotation that exists is validated, but no new pair or
proof-type obligation is invented.

Every artifact reference - ledger observed, finding failure evidence, repair
before/after - goes through the one G6 ``validate_references`` owner over the
snapshot's frozen artifact facts. This module contributes only closure,
association, and sufficiency diagnostics; it never opens a file, never parses
a capture request, and never compares bytes itself. ``artifact_facts=None``
means no evidence authority was supplied at all (no ``--run-root`` /
``--evidence-dir``, no supplied snapshot): the structural reading validates
annotation shape, association, pairing, and the ``evidence/`` prefix, but
does not claim a binding it cannot inspect. Complete acceptance always
supplies the frozen facts, so a stripped snapshot still reports unavailable.

Byte-identical visual halves are ``G4.repair_evidence_unchanged``: the pair is
insufficient to demonstrate the declared visible change. That is not a
statement that the function still fails - the criterion's ledger result decides
function - and changed bytes never establish criterion success either.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from design_playbook.mcp.evidence.ledger_syntax import (
    LedgerFacts,
    artifact_token,
    criterion_token,
    parse_ledger,
)
from design_playbook.scripts._diagnostics import Finding, finding
from design_playbook.scripts.finding_syntax import (
    ClosureFact,
    ClosureRepairAnnotation,
    closure_target_candidates,
    parse_closures,
    parse_findings,
)
from design_playbook.scripts.g1_spec import ProofRequirement
from design_playbook.scripts.g6_evidence import (
    EvidenceReference,
    ReferenceBinding,
    reference_finding,
    validate_references,
)
from design_playbook.scripts.g6_records import (
    EvidenceArtifactFact,
    normalise_evidence_reference,
)
from design_playbook.scripts.stages import EVIDENCE_PREFIX

# One exact criterion token per occurrence. Leading zeros are not the G1
# spelling, so they name no criterion rather than silently mapping onto one.
_CRITERION_TOKEN = re.compile(r"(?i)L6\.([1-9][0-9]*)\Z")
_CRITERIA_SEPARATORS = re.compile(r"[\s,，;；]+")
_VISUAL_PROOFS = frozenset({"screenshot"})
_BOUND_PROOFS = frozenset({"screenshot", "a11y_tree", "interaction_trace"})
_NONVISUAL_PROOFS = frozenset({"automated_check", "declaration_coverage"})


@dataclass(frozen=True)
class _LedgerRetest:
    """The one current ledger row for a criterion, projected for G4."""

    criterion: str
    observed: str
    result: str


def _canonical_criterion(token: str) -> str | None:
    """Exact ``L6.<n>`` shape without converting the digits to an integer.

    The pattern already rejects leading zeros, so the validated digit string
    is canonical as written. Converting it would let an external Markdown token
    with thousands of digits raise the interpreter's int-conversion limit; the
    declared criterion set rejects the unknown number with a named diagnostic.
    """
    match = _CRITERION_TOKEN.fullmatch(token.strip())
    if match is None:
        return None
    return f"L6.{match.group(1)}"


def _criteria_tokens(values) -> list[str]:
    tokens: list[str] = []
    for value in values or ():
        for part in _CRITERIA_SEPARATORS.split(str(value).strip()):
            if part:
                tokens.append(part)
    return tokens


def _finding_criteria(finding: dict[str, list[str]]) -> tuple[list[str], list[Finding]]:
    """Declared criteria tokens plus their association diagnostics."""
    errs: list[Finding] = []
    tokens: list[str] = []
    for token in _criteria_tokens(finding.get("criteria")):
        canonical = _canonical_criterion(token)
        if canonical is None:
            errs.append(_association_missing(
                f"criteria: value {token!r} is not an exact L6.<n> token"))
            continue
        tokens.append(canonical)
    seen: set[str] = set()
    for token in tokens:
        if token in seen:
            errs.append(_association_missing(
                f"criteria: repeats {token}; each criterion may be named once"))
        seen.add(token)
    return tokens, errs


def _resolved_annotation_criterion(
    annotation: ClosureRepairAnnotation,
    finding_dict: dict[str, list[str]],
    requirements: dict[str, ProofRequirement],
) -> str | None:
    """The one criterion an explicit annotation settles, or None when unknown.

    Mirrors the mode paths' resolution: an explicit ``criterion=`` must be a
    declared requirement; otherwise the annotation inherits the finding's
    criterion only when that finding declares exactly one distinct token.
    """
    values = annotation.values("criterion")
    if values:
        criterion = _canonical_criterion(values[0])
        return criterion if criterion in requirements else None
    tokens, _errs = _finding_criteria(finding_dict)
    distinct = list(dict.fromkeys(tokens))
    return distinct[0] if len(distinct) == 1 else None


def _duplicate_annotation_findings(
    *,
    findings: list[dict[str, list[str]]],
    closures: tuple[ClosureFact, ...],
    requirements: dict[str, ProofRequirement],
) -> tuple[list[Finding], set[ClosureRepairAnnotation], set[tuple[int, str]]]:
    """Mode-shared check: one annotation per closure x criterion.

    Duplicate annotations are a structural error in every reading; complete
    acceptance only adds the absent-proof obligation on top. Returns the
    diagnostics, the annotations the check owns, and the flagged
    ``(closure line, criterion)`` keys so the mode paths neither re-report the
    duplicate nor demand the absent pair.
    """
    errs: list[Finding] = []
    owned: set[ClosureRepairAnnotation] = set()
    keys: set[tuple[int, str]] = set()
    for closure in closures:
        candidates = closure_target_candidates(findings, closure.target)
        if len(candidates) != 1:
            continue
        finding_dict = findings[candidates[0]]
        groups: dict[str, list[ClosureRepairAnnotation]] = {}
        for annotation in closure.annotations:
            if _annotation_problems(annotation):
                continue  # the mode paths report the malformed annotation
            criterion = _resolved_annotation_criterion(
                annotation, finding_dict, requirements)
            if criterion is None:
                continue  # unknown association is reported by the mode path
            groups.setdefault(criterion, []).append(annotation)
        for criterion, group in groups.items():
            if len(group) < 2:
                continue
            keys.add((closure.line, criterion))
            owned.update(group)
            errs.append(_repair_finding(
                "G4.repair_evidence_duplicate",
                f"closure {closure.target!r} has {len(group)} repair "
                f"annotations for {criterion}; exactly one pair may settle a "
                "criterion",
                expected="one annotation per closure x criterion",
                actual=str(len(group)),
                repair="Keep one pair; delete the extra annotation",
            ))
    return errs, owned, keys


def _ledger_retests(facts: LedgerFacts) -> dict[str, list[_LedgerRetest]]:
    retests: dict[str, list[_LedgerRetest]] = {}
    for row in facts.rows:
        criterion_values = row.values("criterion")
        if not criterion_values or not criterion_values[0]:
            continue
        token = criterion_token(criterion_values[0])
        result_values = row.values("result")
        retests.setdefault(token, []).append(_LedgerRetest(
            criterion=token,
            observed=row.artifact_token,
            result=result_values[0].casefold() if result_values else "",
        ))
    return retests


def _is_blocking(finding_dict: dict[str, list[str]]) -> bool:
    dispositions = finding_dict.get("disposition") or []
    return bool(dispositions) and dispositions[0].strip().casefold() == "blocking"


def _annotation_problems(annotation: ClosureRepairAnnotation) -> list[str]:
    problems: list[str] = []
    if annotation.unconsumed:
        problems.append("unconsumed text: " + " ".join(annotation.unconsumed))
    if annotation.unknown_fields:
        problems.append("unknown field(s): " + ", ".join(annotation.unknown_fields))
    for name in ("criterion", "before", "after"):
        values = annotation.values(name)
        if len(values) > 1:
            problems.append(f"duplicate {name}")
        elif values and not values[0].strip():
            problems.append(f"empty {name}")
    return problems


def _annotation_finding(
    annotation: ClosureRepairAnnotation, message: str, *,
    expected: str, repair: str,
) -> Finding:
    return finding(
        "G4.repair_evidence_annotation_malformed",
        f"G4 repair-evidence: annotation on line {annotation.line} "
        f"{message}",
        owner="point-back.md#closure",
        expected=expected,
        actual=message,
        repair=repair,
    )


def _association_missing(message: str) -> Finding:
    return finding(
        "G4.repair_association_missing",
        f"G4 repair-evidence: {message}",
        owner="point-back.md#closure",
        expected="the closed blocking finding declares exact L6 criteria and "
                 "one closure resolves to it alone",
        actual=message,
        repair="Name the criterion on the finding (`criteria: L6.<n>`), keep "
               "exactly one exact closure target, and declare the repair "
               "annotation under that closure",
    )


def _requirement_unavailable(criterion: str, reason: str) -> Finding:
    return finding(
        "G4.repair_requirement_unavailable",
        f"G4 repair-evidence: {criterion} {reason}",
        owner="spec.md#L6",
        expected="a known proof requirement with a declared capture type",
        actual=reason,
        repair="Declare `Required evidence: <type>; state=<state>; "
               "viewport=<w>x<h>` on the L6 criterion",
    )


def _repair_finding(code: str, message: str, *, repair: str,
                    expected: str, actual: str) -> Finding:
    return finding(
        code,
        f"G4 repair-evidence: {message}",
        owner="point-back.md#closure",
        expected=expected,
        actual=actual,
        repair=repair,
    )


def _pair_refs(
    annotation: ClosureRepairAnnotation, criterion: str, proof: str | None,
    *, require_hash: bool,
) -> tuple[EvidenceReference, EvidenceReference]:
    """Both pair halves as references for the one G6 verification owner.

    A visible-state pair is two captures of the declared proof type, so both
    halves carry it; the after is also the criterion's retest. Nonvisual
    repairs keep the declared type on the retest only - the finding's failure
    artifact may legitimately be a different proof class.
    """
    before_proof = proof if proof in _VISUAL_PROOFS else None
    return (
        EvidenceReference(criterion, annotation.values("before")[0],
                          role="before", proof=before_proof,
                          require_hash=require_hash),
        EvidenceReference(criterion, annotation.values("after")[0],
                          role="after", proof=proof, require_hash=require_hash),
    )


def _g6_findings(
    references, entries, valid_criteria, artifact_facts,
) -> tuple[list[Finding], dict[str, ReferenceBinding]]:
    """Validate references through G6 and keep the bindings by role."""
    errs: list[Finding] = []
    bindings: dict[str, ReferenceBinding] = {}
    for binding in validate_references(
            references, entries, valid_criteria, artifact_facts):
        bindings[binding.reference.role] = binding
        for diagnostic in binding.diagnostics:
            errs.append(reference_finding(binding, diagnostic))
    return errs, bindings


def _evidence_tokens(finding_dict: dict[str, list[str]]) -> set[str]:
    tokens: set[str] = set()
    for value in finding_dict.get("evidence") or ():
        token = artifact_token(value)
        if token.casefold().startswith(EVIDENCE_PREFIX):
            tokens.add(normalise_evidence_reference(token)[0])
    return tokens


def _canonical(token: str) -> str:
    return normalise_evidence_reference(token)[0]


def _viewports_match(
    before: ReferenceBinding, after: ReferenceBinding,
    declared: tuple[int, int] | None,
) -> bool:
    left, right = before.viewport, after.viewport
    if not isinstance(left, dict) or not isinstance(right, dict):
        return False
    if left != right:
        return False
    if declared is not None:
        width, height = declared
        if left.get("width") != width or left.get("height") != height:
            return False
    return True


def _check_complete_obligation(
    *,
    index: int,
    finding_dict: dict[str, list[str]],
    closure: ClosureFact,
    requirements: dict[str, ProofRequirement],
    retests: dict[str, list[_LedgerRetest]],
    entries: list[dict],
    artifact_facts: tuple[EvidenceArtifactFact, ...] | None,
    duplicate_keys: frozenset[tuple[int, str]] = frozenset(),
) -> tuple[list[Finding], set[ClosureRepairAnnotation]]:
    """One closed blocking finding's complete-acceptance obligation."""
    errs: list[Finding] = []
    consumed: set[ClosureRepairAnnotation] = set()
    criteria, criteria_errs = _finding_criteria(finding_dict)
    errs.extend(criteria_errs)
    if not criteria:
        if not criteria_errs:
            errs.append(_association_missing(
                f"blocking finding {index + 1} is claimed closed by a closure "
                "but declares no criteria:"))
        return errs, consumed
    # Duplicate occurrences are already an association error; evaluate each
    # distinct criterion once so one finding cannot produce duplicate pairs.
    unique_criteria = list(dict.fromkeys(criteria))
    declared: list[str] = []
    for criterion in unique_criteria:
        requirement = requirements.get(criterion)
        if requirement is None:
            errs.append(_requirement_unavailable(
                criterion, "is not declared by the spec's L6 set"))
        elif requirement.availability != "known" or requirement.proof is None:
            errs.append(_requirement_unavailable(
                criterion, f"has no known proof type (availability="
                           f"{requirement.availability})"))
        else:
            declared.append(criterion)
    if not declared:
        return errs, consumed

    annotations: list[ClosureRepairAnnotation] = []
    for annotation in closure.annotations:
        consumed.add(annotation)
        problems = _annotation_problems(annotation)
        if problems:
            errs.append(_annotation_finding(
                annotation, "is malformed: " + "; ".join(problems),
                expected="one criterion=/before=/after= occurrence each",
                repair="Keep exactly one non-empty criterion, before, and "
                       "after; remove unknown fields and stray text"))
            continue
        annotations.append(annotation)

    # Every annotation belongs to one of the finding's shape-valid criteria;
    # only criteria with a known requirement receive an obligation below.
    # A criterion whose requirement is unavailable is already a named
    # diagnostic, so its annotation association must not crash the lookup.
    by_criterion: dict[str, list[ClosureRepairAnnotation]] = {
        criterion: [] for criterion in unique_criteria}
    single = unique_criteria[0] if len(unique_criteria) == 1 else None
    for annotation in annotations:
        values = annotation.values("criterion")
        if values:
            criterion = _canonical_criterion(values[0])
            if criterion is None or criterion not in unique_criteria:
                errs.append(_repair_finding(
                    "G4.repair_evidence_unknown_criterion",
                    f"annotation names criteria {values[0]!r} not declared by "
                    f"this finding",
                    expected="criterion= one of " + ", ".join(unique_criteria),
                    actual=values[0],
                    repair="Name one of the finding's declared criteria, or "
                           "declare the criterion on the finding",
                ))
                continue
        elif single is not None:
            criterion = single
        else:
            errs.append(_association_missing(
                "an annotation has no criterion= and the finding declares "
                "several criteria"))
            continue
        by_criterion[criterion].append(annotation)

    valid_criteria = set(requirements)
    for criterion in declared:
        if (closure.line, criterion) in duplicate_keys:
            # The mode-shared structural phase already reported the duplicate;
            # this criterion has no single pair to evaluate.
            continue
        requirement = requirements[criterion]
        proof = requirement.proof
        rows = retests.get(criterion, [])
        if len(rows) != 1:
            errs.append(_repair_finding(
                "G4.repair_evidence_retest",
                f"{criterion} has {len(rows)} current ledger rows; the repair "
                "obligation needs exactly one",
                expected="exactly one current ledger row for the criterion",
                actual=str(len(rows)),
                repair="Keep one criterion/required/observed/result row per "
                       "criterion",
            ))
        else:
            row = rows[0]
            if row.result != "pass":
                errs.append(_repair_finding(
                    "G4.repair_evidence_result",
                    f"{criterion} current ledger result is {row.result!r}, not "
                    "pass",
                    expected="result: pass after the repair",
                    actual=row.result or "missing",
                    repair="Fix the criterion or keep the run in Recirculate; "
                           "a changed pair never substitutes for a passing "
                           "re-evaluation",
                ))
            if proof in _BOUND_PROOFS and not row.observed.casefold().startswith(
                    EVIDENCE_PREFIX):
                errs.append(_repair_finding(
                    "G4.repair_evidence_after",
                    f"{criterion} observed names no evidence artifact to bind "
                    f"the {proof} retest",
                    expected="observed: evidence/<artifact>",
                    actual=row.observed or "empty",
                    repair=f"Capture and bind the {proof} retest artifact, "
                           "then cite it in the ledger",
                ))
        candidates = by_criterion.get(criterion, [])
        if proof in _VISUAL_PROOFS and not candidates:
            errs.append(_repair_finding(
                "G4.repair_evidence_missing",
                f"{criterion} needs one named before/after pair and the "
                "closure declares none",
                expected=f"repair-evidence: criterion={criterion} "
                         "before=<failure> after=<repaired>",
                actual="no annotation",
                repair="Declare the visible-state pair under this closure",
            ))

        annotation = candidates[0] if len(candidates) == 1 else None
        if annotation is not None and _unpaired(annotation):
            errs.append(_repair_finding(
                "G4.repair_evidence_unpaired",
                f"{criterion} declares {'/'.join(_unpaired(annotation))} "
                "without the other half",
                expected="before=<artifact> after=<artifact>",
                actual="missing " + "/".join(_unpaired(annotation)),
                repair="Bind both halves; an unpaired closure is blocked, not "
                       "passed",
            ))
            annotation = None
        if annotation is None:
            errs.extend(_check_retest_only(
                criterion, proof, rows, valid_criteria, entries,
                artifact_facts, requirement.viewport))
            continue
        errs.extend(_check_pair(
            finding_dict=finding_dict,
            criterion=criterion,
            proof=proof,
            declared_viewport=requirement.viewport,
            annotation=annotation,
            rows=rows,
            valid_criteria=valid_criteria,
            entries=entries,
            artifact_facts=artifact_facts,
        ))
    return errs, consumed


def _unpaired(annotation: ClosureRepairAnnotation) -> list[str]:
    return [half for half in ("before", "after")
            if not annotation.values(half)]


def _check_retest_only(
    criterion: str, proof: str | None, rows: list[_LedgerRetest],
    valid_criteria: set[str], entries: list[dict],
    artifact_facts: tuple[EvidenceArtifactFact, ...] | None,
    declared_viewport: tuple[int, int] | None = None,
) -> list[Finding]:
    """Validate the current retest when no pair is declared or possible.

    Captured retests keep the criterion's explicitly declared viewport even
    when no screenshot pair is required. Text-only observations never reach
    the binding comparison, so they gain no viewport obligation.
    """
    if len(rows) != 1 or proof is None:
        return []
    observed = rows[0].observed
    if proof in _BOUND_PROOFS:
        if not observed.casefold().startswith(EVIDENCE_PREFIX):
            return []
        references = [EvidenceReference(
            criterion, observed, role="after", proof=proof)]
    elif proof in _NONVISUAL_PROOFS:
        if not observed.casefold().startswith(EVIDENCE_PREFIX):
            return []
        references = [EvidenceReference(criterion, observed, role="after")]
    else:
        return []
    errs, bindings = _g6_findings(
        references, entries, valid_criteria, artifact_facts)
    binding = bindings.get("after")
    if (declared_viewport is not None and binding is not None
            and not binding.diagnostics):
        width, height = declared_viewport
        viewport = binding.viewport
        if (not isinstance(viewport, dict)
                or viewport.get("width") != width
                or viewport.get("height") != height):
            errs.append(_repair_finding(
                "G4.repair_evidence_mismatch",
                f"{criterion} retest viewport {viewport!r} does not match the "
                f"declared {width}x{height}",
                expected=f"capture viewport {width}x{height}",
                actual=repr(viewport),
                repair="Recapture the retest at the criterion's declared "
                       "viewport, or correct the declaration",
            ))
    return errs


def _check_pair(
    *,
    finding_dict: dict[str, list[str]],
    criterion: str,
    proof: str | None,
    declared_viewport: tuple[int, int] | None,
    annotation: ClosureRepairAnnotation,
    rows: list[_LedgerRetest],
    valid_criteria: set[str],
    entries: list[dict],
    artifact_facts: tuple[EvidenceArtifactFact, ...] | None,
) -> list[Finding]:
    """Validate one declared pair against the finding, ledger, and G6."""
    errs: list[Finding] = []
    before_ref, after_ref = _pair_refs(
        annotation, criterion, proof, require_hash=proof in _VISUAL_PROOFS)
    refs = [before_ref, after_ref]
    g6_errs, bindings = _g6_findings(
        refs, entries, valid_criteria, artifact_facts)
    errs.extend(g6_errs)

    evidence_tokens = _evidence_tokens(finding_dict)
    if _canonical(before_ref.token) not in evidence_tokens:
        errs.append(_repair_finding(
            "G4.repair_evidence_before",
            f"{criterion} before={before_ref.token} is not this finding's "
            "failure evidence",
            expected="before= one of the finding's `evidence:` artifacts",
            actual=before_ref.token,
            repair="Point before at the artifact recorded on the finding; a "
                   "pair borrowed from another closure settles nothing",
        ))
    if len(rows) == 1 and _canonical(after_ref.token) != _canonical(rows[0].observed):
        errs.append(_repair_finding(
            "G4.repair_evidence_after",
            f"{criterion} after={after_ref.token} is not the criterion's "
            "current observed artifact",
            expected=f"after={rows[0].observed}",
            actual=after_ref.token,
            repair="After must be the exact artifact the current ledger row "
                   "observes; changed bytes never substitute for the retest",
        ))

    before_binding = bindings.get("before")
    after_binding = bindings.get("after")
    if before_binding is None or after_binding is None:
        return errs
    if (not before_binding.diagnostics and not after_binding.diagnostics
            and not _viewports_match(
                before_binding, after_binding, declared_viewport)):
        errs.append(_repair_finding(
            "G4.repair_evidence_mismatch",
            f"{criterion} before/after do not share one complete viewport"
            + (f" {declared_viewport}" if declared_viewport else ""),
            expected="same request.viewport on both halves"
                     + (f" matching the spec's {declared_viewport}"
                        if declared_viewport else ""),
            actual=f"before={before_binding.viewport!r} "
                   f"after={after_binding.viewport!r}",
            repair="Recapture both halves at the failing criterion's one "
                   "viewport",
        ))
    if (proof in _VISUAL_PROOFS
            and not before_binding.diagnostics
            and not after_binding.diagnostics
            and before_binding.sha256 is not None
            and before_binding.sha256 == after_binding.sha256):
        errs.append(finding(
            "G4.repair_evidence_unchanged",
            f"G4 repair-evidence: {criterion} before and after are "
            "byte-identical, so the pair is insufficient to demonstrate the "
            "declared visible repair",
            owner="point-back.md#closure",
            expected="a repaired capture that visibly differs from the "
                     "failure capture",
            actual="identical sha256",
            repair="Recapture after the fix; functional status still comes "
                   "from the criterion's ledger result, not from the bytes",
        ))
    return errs


def _check_legacy_annotation(
    *,
    annotation: ClosureRepairAnnotation,
    candidates: tuple[int, ...],
    findings: list[dict[str, list[str]]],
    requirements: dict[str, ProofRequirement],
    entries: list[dict],
    artifact_facts: tuple[EvidenceArtifactFact, ...] | None,
) -> list[Finding]:
    """Structural reading: validate what exists, invent no new obligation."""
    errs: list[Finding] = []
    problems = _annotation_problems(annotation)
    if problems:
        return [_annotation_finding(
            annotation, "is malformed: " + "; ".join(problems),
            expected="one criterion=/before=/after= occurrence each",
            repair="Keep one non-empty criterion, before, and after; remove "
                   "unknown fields and stray text")]
    if len(candidates) != 1:
        return [_association_missing(
            f"repair annotation on line {annotation.line} belongs to a "
            f"closure that resolves to {len(candidates)} findings")]
    finding_dict = findings[candidates[0]]
    values = annotation.values("criterion")
    criterion: str | None = None
    if values:
        criterion = _canonical_criterion(values[0])
        if criterion is None or criterion not in requirements:
            return [_repair_finding(
                "G4.repair_evidence_unknown_criterion",
                f"annotation names criteria {values[0]!r}, which the spec "
                "does not declare",
                expected="criterion= a declared L6.<n>",
                actual=values[0],
                repair="Name a declared criterion; unknown criteria cannot be "
                       "cleared by a pair",
            )]
    else:
        inherited, criteria_errs = _finding_criteria(finding_dict)
        errs.extend(criteria_errs)
        if len(inherited) == 1:
            criterion = inherited[0]
        else:
            errs.append(_association_missing(
                f"annotation on line {annotation.line} has no criterion= and "
                "its finding declares no single criterion to inherit"))
            return errs
    requirement = requirements.get(criterion)
    proof = (requirement.proof
             if requirement is not None and requirement.availability == "known"
             else None)
    missing = _unpaired(annotation)
    if missing:
        errs.append(_repair_finding(
            "G4.repair_evidence_unpaired",
            f"{criterion} declares {'/'.join(missing)} without the other half",
            expected="before=<artifact> after=<artifact>",
            actual="missing " + "/".join(missing),
            repair="Bind both halves; an unpaired closure is blocked, not "
                   "passed",
        ))
        return errs
    before_ref, after_ref = _pair_refs(
        annotation, criterion, None, require_hash=False)
    if artifact_facts is None:
        # Structural reading with no evidence authority (no --run-root /
        # --evidence-dir, no supplied snapshot): G6's conditional gate is off,
        # so bindability cannot be judged. The tokens must still be
        # evidence-relative; shape and pairing were checked above.
        bindings = validate_references(
            [before_ref, after_ref], entries, set(requirements), None)
        for binding in bindings:
            for diagnostic in binding.diagnostics:
                if diagnostic.code == "reference_prefix":
                    errs.append(reference_finding(binding, diagnostic))
        return errs
    g6_errs, bindings = _g6_findings(
        [before_ref, after_ref], entries, set(requirements), artifact_facts)
    errs.extend(g6_errs)
    before_binding = bindings.get("before")
    after_binding = bindings.get("after")
    if before_binding is None or after_binding is None:
        return errs
    if (not before_binding.diagnostics and not after_binding.diagnostics
            and not _viewports_match(before_binding, after_binding, None)):
        errs.append(_repair_finding(
            "G4.repair_evidence_mismatch",
            f"{criterion} before/after do not share one complete viewport",
            expected="same request.viewport on both halves",
            actual=f"before={before_binding.viewport!r} "
                   f"after={after_binding.viewport!r}",
            repair="Recapture both halves at one viewport",
        ))
    if (proof in _VISUAL_PROOFS
            and not before_binding.diagnostics
            and not after_binding.diagnostics
            and before_binding.sha256 is not None
            and before_binding.sha256 == after_binding.sha256):
        errs.append(finding(
            "G4.repair_evidence_unchanged",
            f"G4 repair-evidence: {criterion} before and after are "
            "byte-identical, so the pair is insufficient to demonstrate the "
            "declared repair",
            owner="point-back.md#closure",
            expected="a repaired capture that differs from the failure capture",
            actual="identical sha256",
            repair="Recapture after the fix; changed bytes alone never "
                   "establish criterion success either",
        ))
    return errs


def check_repair_evidence(
    text: str,
    entries: list[dict] | None = None,
    *,
    requirements: tuple[ProofRequirement, ...] = (),
    ledger: LedgerFacts | None = None,
    artifact_facts: tuple[EvidenceArtifactFact, ...] | None = None,
    require_complete: bool = False,
) -> list[Finding]:
    """Return G4 repair-evidence findings over one immutable snapshot.

    ``requirements`` is the G1 proof-requirement projection; its criterion set
    is the declared L6 universe. ``ledger`` and ``artifact_facts`` come from
    the same capture as ``text``; an empty tuple fails every reference as
    unavailable and is never re-read, while ``None`` means no evidence
    authority was supplied, so the structural reading skips binding checks.
    ``require_complete`` is set from the same complete-profile value as the
    CLI's other complete-acceptance requirements - it is never inferred from
    the individual ``--require-*`` flags.
    """
    findings = parse_findings(text)
    closure_facts = parse_closures(text)
    ledger_facts = ledger or parse_ledger(text)
    requirement_map = {item.criterion: item for item in requirements}
    retests = _ledger_retests(ledger_facts)
    entries = list(entries or ())
    errs: list[Finding] = []

    for annotation in closure_facts.orphan_annotations:
        errs.append(finding(
            "G4.repair_evidence_orphan",
            f"G4 repair-evidence: annotation on line {annotation.line} has no "
            "belonging closure",
            owner="point-back.md#closure",
            expected="a repair annotation indented under its closure line",
            actual="orphan annotation",
            repair="Indent the annotation under the closure it belongs to, or "
                   "delete it; it never settles another closure",
        ))

    matched: dict[int, list[ClosureFact]] = {}
    for closure in closure_facts.closures:
        for index in closure_target_candidates(findings, closure.target):
            matched.setdefault(index, []).append(closure)

    # Duplicate explicit annotations are structural in every mode; complete
    # acceptance keeps only the absent-required-proof obligation.
    duplicate_errs, duplicate_owned, duplicate_keys = (
        _duplicate_annotation_findings(
            findings=findings, closures=closure_facts.closures,
            requirements=requirement_map))
    errs.extend(duplicate_errs)

    consumed: set[ClosureRepairAnnotation] = set()
    if require_complete:
        for index, finding_dict in enumerate(findings):
            if not _is_blocking(finding_dict):
                continue
            closures = matched.get(index, [])
            if not closures:
                continue
            if len(closures) > 1:
                errs.append(_association_missing(
                    f"blocking finding {index + 1} is claimed closed by "
                    f"{len(closures)} closures; exactly one may close it"))
                continue
            closure = closures[0]
            if len(closure_target_candidates(findings, closure.target)) != 1:
                errs.append(_association_missing(
                    f"closure {closure.target!r} resolves to several findings; "
                    "a shared identity cannot close any of them"))
                continue
            obligation_errs, obligation_consumed = _check_complete_obligation(
                index=index,
                finding_dict=finding_dict,
                closure=closure,
                requirements=requirement_map,
                retests=retests,
                entries=entries,
                artifact_facts=artifact_facts,
                duplicate_keys=frozenset(duplicate_keys),
            )
            errs.extend(obligation_errs)
            consumed.update(obligation_consumed)

    for closure in closure_facts.closures:
        candidates = closure_target_candidates(findings, closure.target)
        for annotation in closure.annotations:
            if annotation in consumed or annotation in duplicate_owned:
                continue
            errs.extend(_check_legacy_annotation(
                annotation=annotation,
                candidates=candidates,
                findings=findings,
                requirements=requirement_map,
                entries=entries,
                artifact_facts=artifact_facts,
            ))
    return errs