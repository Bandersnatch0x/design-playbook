"""G2-G4 point-back gates (ADR-0023 + vNext S1 review axis).

Owns the point-back / verdict / closure rule sets: every L6 item has one
complete evidence row and every finding has issue/source/fix/severity (G2),
one explicit verdict with Pass requiring all evidence to pass (G3), and
closure-trail coverage preventing blockers being dropped (G4).

vNext S1 (review-prototype Q1/Q4): findings may carry additional field
lines (track / confidence / disposition / evidence / assumes / rule / dd).
The four required fields and the machine face are unchanged; additional
fields are validated only when present.

vNext S5 (vnext-prototype Q5=B, second stage — BREAKING): the legacy
severity aliases ``high (blocking) | high | med | low`` are no longer
legal. The value domain is the new axis ``S3 | S2 | S1 | S0`` only;
legacy spellings are structural errors. Blocking disposition comes from
the ``disposition: blocking`` field — severity and disposition are two
axes.
"""
from __future__ import annotations

import re

from design_playbook.scripts._diagnostics import Finding, finding
from design_playbook.mcp.evidence.ledger_syntax import EVIDENCE_FIELDS, LedgerFacts, parse_ledger
from design_playbook.scripts.verdict_syntax import VerdictFacts, parse_verdict

FINDING_FIELDS = ("issue", "source", "fix", "severity")
EXTRA_FINDING_FIELDS = (
    "track", "confidence", "disposition", "evidence", "assumes", "rule", "dd",
    # vNext S3 interaction-track annotations (review-prototype 1.2): the
    # dimension refinement plus its objective/subjective face and judgment
    # source. Validated by interaction_dimensions.py; parsed here so every
    # consumer sees the same field set.
    "dimension", "face", "basis",
    # vNext S4 recirculation annotations (loop-prototype 2.2 / 7.1): the
    # second-hop repair route (R1 | R2-line | R2-structural | R3 | R4 | R5,
    # multiple values legal for multi-layer findings) and the machine round
    # counter for blocking findings (rounds survived through repair +
    # re-evaluate). Validated by repair_rounds.py / escalation_signals.py /
    # g12_tier_boundary.py; parsed here so every consumer sees one field set.
    "route", "rounds",
)
FIELD_LINE = re.compile(
    r"^(issue|source|fix|severity|track|confidence|disposition|evidence|"
    r"assumes|rule|dd|dimension|face|basis|route|rounds):[ \t]*(.*)$",
    re.I | re.M)
CLOSURE_LINE = re.compile(
    r"^\s*[-*]\s*closes:[ \t]*(.*?)[ \t]*->[^\n]*\b0 blocking\b",
    re.I | re.M,
)
VALID_RESULTS = {"pass", "fail", "blocked", "n/a"}

# Severity axis (review-prototype Q1). vNext S5 removed the legacy aliases
# (vnext-prototype Q5=B, two-stage migration complete): only S3|S2|S1|S0 are
# legal; the old spellings are structural errors.
SEVERITY_NEW = frozenset({"S3", "S2", "S1", "S0"})
SEVERITY_LEGACY = frozenset({"high (blocking)", "high", "med", "low"})
VALID_TRACKS = frozenset({"product", "interaction", "cross-cutting"})
VALID_CONFIDENCE = frozenset({"high", "medium", "low"})
VALID_DISPOSITIONS = frozenset({"blocking", "advisory", "info"})


def severity_axis(value: str) -> str | None:
    """Map a severity value onto the axis; None when invalid.

    The exact axis spelling is required — the legacy aliases were removed
    in vNext S5 (they used to fold onto S3/S2/S1/S1 during the alias
    period).
    """
    stripped = value.strip()
    if stripped in SEVERITY_NEW:
        return stripped
    return None


def _findings(text: str) -> list[dict[str, list[str]]]:
    """Parse finding paragraphs without using a required field as delimiter.

    Additional-field-only blocks (e.g. a bare ``track:`` line outside a
    finding) do not count as findings — at least one of the four required
    fields must be present.
    """
    findings = []
    for block in re.split(r"\n\s*\n", text):
        matches = FIELD_LINE.findall(block)
        if not matches:
            continue
        fields = {field: [] for field in FINDING_FIELDS + EXTRA_FINDING_FIELDS}
        for name, value in matches:
            fields[name.lower()].append(value.strip())
        if not any(fields[field] for field in FINDING_FIELDS):
            continue
        findings.append(fields)
    return findings


def _check_evidence(
        text: str, expected_l6: int, is_pass: bool,
        ledger_facts: LedgerFacts | None = None) -> list[Finding]:
    errs: list[Finding] = []
    rows = (ledger_facts or parse_ledger(text)).rows
    if not rows:
        return [finding(
            "G2.no_evidence_rows",
            "G2 evidence: no criterion-shaped ledger entries",
            owner="point-back.md#evidence",
            expected="one evidence row per L6 criterion",
            actual="0 rows",
            repair="Add criterion/required/observed/result rows for each L6 item",
        )]

    seen_l6: dict[int, int] = {}
    for i, row in enumerate(rows, 1):
        for field in EVIDENCE_FIELDS:
            values = row.values(field)
            if not values:
                errs.append(finding(
                    "G2.missing_field",
                    f"G2 evidence: row {i} missing {field}:",
                    owner=f"point-back.md#evidence.row{i}",
                    expected=f"{field}: value",
                    actual="missing",
                    repair=f"Add {field}: on evidence row {i}",
                ))
            elif not any(values):
                errs.append(finding(
                    "G2.empty_field",
                    f"G2 evidence: row {i} has empty {field}",
                    owner=f"point-back.md#evidence.row{i}",
                    expected=f"non-empty {field}",
                    actual="empty",
                    repair=f"Fill {field} on evidence row {i}",
                ))
            elif len(values) > 1:
                errs.append(finding(
                    "G2.repeated_field",
                    f"G2 evidence: row {i} repeats {field}:",
                    owner=f"point-back.md#evidence.row{i}",
                    expected=f"single {field}",
                    actual=f"{len(values)} values",
                    repair=f"Keep one {field} on evidence row {i}",
                ))

        criterion_values = row.values("criterion")
        criterion = criterion_values[0] if criterion_values else ""
        result_values = row.values("result")
        result_raw = result_values[0] if result_values else ""
        result = result_raw.casefold()
        if result and result not in VALID_RESULTS:
            errs.append(finding(
                "G2.invalid_result",
                f"G2 evidence: row {i} has invalid result '{result_raw}'",
                owner=f"point-back.md#evidence.row{i}",
                expected="pass|fail|blocked|n/a",
                actual=result_raw,
                repair=f"Set result on row {i} to an allowed value",
            ))
        if is_pass and result and result != "pass":
            errs.append(finding(
                "G3.pass_requires_result",
                f"G3 evidence: Pass requires row {i} result pass, got "
                f"'{result_raw}'",
                owner=f"point-back.md#evidence.row{i}",
                expected="pass",
                actual=result_raw,
                repair="Change verdict to Recirculate or fix the failed evidence",
            ))

        l6_ref = re.fullmatch(r"L6\.(\d+)", criterion.strip(), re.I)
        if not l6_ref and criterion:
            errs.append(finding(
                "G2.criterion_shape",
                f"G2 evidence: row {i} criterion must be exactly L6.<n>, got "
                f"'{criterion}'",
                owner=f"point-back.md#evidence.row{i}",
                expected="L6.<n>",
                actual=criterion,
                repair=f"Set criterion on row {i} to L6.<n>",
            ))
        elif l6_ref:
            number = int(l6_ref.group(1))
            seen_l6[number] = seen_l6.get(number, 0) + 1

    for number in range(1, expected_l6 + 1):
        count = seen_l6.get(number, 0)
        if count == 0:
            errs.append(finding(
                "G2.missing_l6_row",
                f"G2 evidence: missing ledger row for L6.{number}",
                owner="point-back.md#evidence",
                expected=f"row for L6.{number}",
                actual="missing",
                repair=f"Add an evidence row for L6.{number}",
            ))
        elif count > 1:
            errs.append(finding(
                "G2.repeated_l6_row",
                f"G2 evidence: repeated ledger rows for L6.{number}",
                owner="point-back.md#evidence",
                expected="exactly one row",
                actual=str(count),
                repair=f"Keep a single evidence row for L6.{number}",
            ))
    for number in sorted(set(seen_l6) - set(range(1, expected_l6 + 1))):
        errs.append(finding(
            "G2.unknown_l6",
            f"G2 evidence: ledger references unknown L6.{number}",
            owner="point-back.md#evidence",
            expected=f"L6.1..L6.{expected_l6}",
            actual=f"L6.{number}",
            repair="Remove the unknown L6 row or add the criterion to the spec",
        ))
    return errs


def _normalise_issue(value: str) -> str:
    return " ".join(value.casefold().split())


def _verdict(
        text: str, verdict_facts: VerdictFacts | None = None
) -> tuple[str | None, list[Finding]]:
    # Verdict syntax facts are parsed once in verdict_syntax (ADR-0025); G3
    # retains its diagnostic mapping and projects from the shared facts so
    # rule IDs, messages, finding order, and accepted value forms stay
    # compatible with the prior independent parser.
    facts = verdict_facts or parse_verdict(text)
    if facts.heading_count == 0:
        return None, [finding(
            "G3.missing_verdict",
            "G3 point-back: missing explicit Verdict section",
            owner="point-back.md#Verdict",
            expected="## Verdict with Pass or Recirculate",
            actual="missing",
            repair="Add an explicit Verdict section",
        )]
    if facts.heading_count > 1:
        return None, [finding(
            "G3.repeated_verdict",
            "G3 point-back: repeated Verdict section",
            owner="point-back.md#Verdict",
            expected="exactly one Verdict section",
            actual=str(facts.heading_count),
            repair="Keep a single Verdict section",
        )]
    if facts.value_count != 1:
        return None, [finding(
            "G3.verdict_count",
            "G3 point-back: Verdict section must contain exactly one "
            "Pass or Recirculate verdict",
            owner="point-back.md#Verdict",
            expected="exactly one Pass or Recirculate",
            actual=str(facts.value_count),
            repair="State exactly one Pass or Recirculate verdict",
        )]
    return facts.canonical, []


def check_pointback(
        text: str, expected_l6: int, *,
        ledger_facts: LedgerFacts | None = None,
        verdict_facts: VerdictFacts | None = None) -> list[Finding]:
    errs: list[Finding] = []
    pb_findings = _findings(text)
    verdict, verdict_errs = _verdict(text, verdict_facts)
    errs += verdict_errs
    is_pass = verdict == "pass"
    errs += _check_evidence(text, expected_l6, is_pass, ledger_facts)
    if not pb_findings:
        if not is_pass:
            errs.append(finding(
                "G3.no_findings_without_pass",
                "G3 point-back: no findings and no Pass verdict",
                owner="point-back.md",
                expected="Pass verdict or at least one finding",
                actual="no findings and not Pass",
                repair="Set Verdict to Pass or record findings",
            ))
        return errs

    blocking: list[tuple[int, str]] = []
    for i, pb_finding in enumerate(pb_findings, 1):
        for field in FINDING_FIELDS:
            values = pb_finding[field]
            if not values:
                errs.append(finding(
                    "G2.finding_missing_field",
                    f"G2 point-back: finding {i} missing {field}:",
                    owner=f"point-back.md#finding.{i}",
                    expected=f"{field}: value",
                    actual="missing",
                    repair=f"Add {field}: on finding {i}",
                ))
            elif not any(values):
                suffix = " (breaks routing)" if field == "source" else ""
                errs.append(finding(
                    "G2.finding_empty_field",
                    f"G2 point-back: finding {i} has empty {field}{suffix}",
                    owner=f"point-back.md#finding.{i}",
                    expected=f"non-empty {field}",
                    actual="empty",
                    repair=f"Fill {field} on finding {i}",
                ))
            elif len(values) > 1:
                errs.append(finding(
                    "G2.finding_repeated_field",
                    f"G2 point-back: finding {i} repeats {field}:",
                    owner=f"point-back.md#finding.{i}",
                    expected=f"single {field}",
                    actual=f"{len(values)} values",
                    repair=f"Keep one {field} on finding {i}",
                ))

        # Severity axis (vNext S5: new-axis-only; the legacy aliases are
        # structural errors — the two-stage alias period is over).
        severity = pb_finding["severity"][0] if pb_finding["severity"] else ""
        if severity and severity_axis(severity) is None:
            legacy_note = (
                " (legacy alias removed in v0.20.0)" 
                if severity.strip().casefold() in SEVERITY_LEGACY else ""
            )
            errs.append(finding(
                "G2.finding_invalid_severity",
                f"G2 point-back: finding {i} severity '{severity}' is not "
                f"S3|S2|S1|S0{legacy_note}",
                owner=f"point-back.md#finding.{i}",
                expected="S3|S2|S1|S0",
                actual=severity,
                repair="Use the severity axis S3|S2|S1|S0; the legacy "
                       "high (blocking)|high|med|low spellings were "
                       "removed (former aliases: S3/S2/S1/S1)",
            ))

        # Additional fields validate only when present (protocol additive).
        track = pb_finding["track"][0] if pb_finding["track"] else ""
        if track and track.casefold() not in VALID_TRACKS:
            errs.append(finding(
                "G2.finding_invalid_track",
                f"G2 point-back: finding {i} track '{track}' not in "
                "product|interaction|cross-cutting",
                owner=f"point-back.md#finding.{i}",
                expected="product|interaction|cross-cutting",
                actual=track,
                repair="Name the review track that owns this finding",
            ))
        confidence = (
            pb_finding["confidence"][0] if pb_finding["confidence"] else ""
        )
        if confidence and confidence.casefold() not in VALID_CONFIDENCE:
            errs.append(finding(
                "G2.finding_invalid_confidence",
                f"G2 point-back: finding {i} confidence '{confidence}' not "
                "in high|medium|low",
                owner=f"point-back.md#finding.{i}",
                expected="high|medium|low",
                actual=confidence,
                repair="Derive confidence from evidence layers / "
                       "reproducibility / judging subject",
            ))
        dispositions = pb_finding["disposition"]
        if dispositions and len(dispositions) > 1:
            errs.append(finding(
                "G2.finding_repeated_field",
                f"G2 point-back: finding {i} repeats disposition:",
                owner=f"point-back.md#finding.{i}",
                expected="single disposition",
                actual=f"{len(dispositions)} values",
                repair=f"Keep one disposition on finding {i}",
            ))
        disposition = dispositions[0] if dispositions else ""
        if disposition and disposition.casefold() not in VALID_DISPOSITIONS:
            errs.append(finding(
                "G2.finding_invalid_disposition",
                f"G2 point-back: finding {i} disposition '{disposition}' "
                "not in blocking|advisory|info",
                owner=f"point-back.md#finding.{i}",
                expected="blocking|advisory|info",
                actual=disposition,
                repair="Derive disposition from severity x class x "
                       "confidence; judgment-class S3 is never blocking",
            ))
        # New-axis S3 (exact spelling) requires the disposition field; there
        # is no legacy spelling carrying blocking meaning any more.
        if severity.strip() in SEVERITY_NEW and severity_axis(severity) == "S3" \
                and not disposition:
            errs.append(finding(
                "G2.s3_needs_disposition",
                f"G2 point-back: finding {i} uses S3 severity without a "
                "disposition field",
                owner=f"point-back.md#finding.{i}",
                expected="disposition: blocking|advisory",
                actual="missing",
                repair="State the disposition; judgment-class S3 findings "
                       "escalate to the user instead of blocking",
            ))

        # Blocking is the explicit blocking disposition on the axis (severity
        # and disposition are independent axes; a bare S3 does not block
        # without disposition).
        if disposition.casefold() == "blocking":
            issue = pb_finding["issue"][0] if pb_finding["issue"] else ""
            blocking.append((i, issue))

    if is_pass and blocking:
        closure_targets = [
            _normalise_issue(target) for target in CLOSURE_LINE.findall(text)
        ]
        if not closure_targets:
            errs.append(finding(
                "G4.missing_closure_trail",
                "G4 point-back: Pass verdict but no '0 blocking' closure trail",
                owner="point-back.md#closure",
                expected="closes: <issue> -> 0 blocking",
                actual="missing",
                repair="Record a 0-blocking closure for each blocking finding",
            ))
        else:
            known_targets = {_normalise_issue(issue) for _, issue in blocking}
            for i, issue in blocking:
                target = _normalise_issue(issue)
                matches = closure_targets.count(target)
                if matches == 0:
                    errs.append(finding(
                        "G4.unmatched_closure",
                        f"G4 point-back: blocking finding {i} has no matching "
                        f"closure trail for issue '{issue}'",
                        owner=f"point-back.md#finding.{i}",
                        expected=f"closes: {issue} -> 0 blocking",
                        actual="no matching closure",
                        repair=f"Add a closure trail for issue '{issue}'",
                    ))
                elif matches > 1:
                    errs.append(finding(
                        "G4.duplicate_closure",
                        f"G4 point-back: blocking finding {i} has {matches} "
                        f"matching closure trails for issue '{issue}'",
                        owner=f"point-back.md#finding.{i}",
                        expected="exactly one matching closure",
                        actual=str(matches),
                        repair=f"Keep one closure trail for issue '{issue}'",
                    ))
            for target in sorted(set(closure_targets) - known_targets):
                errs.append(finding(
                    "G4.orphan_closure",
                    "G4 point-back: closure trail targets no blocking finding: "
                    f"'{target}'",
                    owner="point-back.md#closure",
                    expected="closure targets a blocking finding issue",
                    actual=target,
                    repair="Remove the orphan closure or restore the finding",
                ))
    return errs
