"""G2-G4 point-back gates (ADR-0023).

Owns the point-back / verdict / closure rule sets: every L6 item has one
complete evidence row and every finding has issue/source/fix/severity (G2),
one explicit verdict with Pass requiring all evidence to pass (G3), and
closure-trail coverage preventing blockers being dropped (G4).
"""
from __future__ import annotations

import re

from design_playbook.scripts._diagnostics import Finding, finding

FINDING_FIELDS = ("issue", "source", "fix", "severity")
FIELD_LINE = re.compile(
    r"^(issue|source|fix|severity):[ \t]*(.*)$", re.I | re.M)
CLOSURE_LINE = re.compile(
    r"^\s*[-*]\s*closes:[ \t]*(.*?)[ \t]*->[^\n]*\b0 blocking\b",
    re.I | re.M,
)
EVIDENCE_FIELDS = ("criterion", "required", "observed", "result")
EVIDENCE_LINE = re.compile(
    r"^(criterion|required|observed|result):[ \t]*(.*)$", re.I | re.M)
VALID_RESULTS = {"pass", "fail", "blocked", "n/a"}


def _findings(text: str) -> list[dict[str, list[str]]]:
    """Parse finding paragraphs without using a required field as delimiter."""
    findings = []
    for block in re.split(r"\n\s*\n", text):
        matches = FIELD_LINE.findall(block)
        if not matches:
            continue
        fields = {field: [] for field in FINDING_FIELDS}
        for name, value in matches:
            fields[name.lower()].append(value.strip())
        findings.append(fields)
    return findings


def _evidence(text: str) -> list[dict[str, list[str]]]:
    rows = []
    for block in re.split(r"\n\s*\n", text):
        matches = EVIDENCE_LINE.findall(block)
        if not matches:
            continue
        fields = {field: [] for field in EVIDENCE_FIELDS}
        for name, value in matches:
            fields[name.lower()].append(value.strip())
        rows.append(fields)
    return rows


def _check_evidence(
        text: str, expected_l6: int, is_pass: bool) -> list[Finding]:
    errs: list[Finding] = []
    rows = _evidence(text)
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
            values = row[field]
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

        criterion = row["criterion"][0] if row["criterion"] else ""
        result = row["result"][0].casefold() if row["result"] else ""
        if result and result not in VALID_RESULTS:
            errs.append(finding(
                "G2.invalid_result",
                f"G2 evidence: row {i} has invalid result '{row['result'][0]}'",
                owner=f"point-back.md#evidence.row{i}",
                expected="pass|fail|blocked|n/a",
                actual=row["result"][0],
                repair=f"Set result on row {i} to an allowed value",
            ))
        if is_pass and result and result != "pass":
            errs.append(finding(
                "G3.pass_requires_result",
                f"G3 evidence: Pass requires row {i} result pass, got "
                f"'{row['result'][0]}'",
                owner=f"point-back.md#evidence.row{i}",
                expected="pass",
                actual=row["result"][0],
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


def _verdict(text: str) -> tuple[str | None, list[Finding]]:
    headings = list(re.finditer(r"^#+\s*Verdict\s*$", text, re.I | re.M))
    if not headings:
        return None, [finding(
            "G3.missing_verdict",
            "G3 point-back: missing explicit Verdict section",
            owner="point-back.md#Verdict",
            expected="## Verdict with Pass or Recirculate",
            actual="missing",
            repair="Add an explicit Verdict section",
        )]
    if len(headings) > 1:
        return None, [finding(
            "G3.repeated_verdict",
            "G3 point-back: repeated Verdict section",
            owner="point-back.md#Verdict",
            expected="exactly one Verdict section",
            actual=str(len(headings)),
            repair="Keep a single Verdict section",
        )]

    start = headings[0].end()
    next_heading = re.search(r"^#+\s+", text[start:], re.M)
    end = start + next_heading.start() if next_heading else len(text)
    body = text[start:end]
    values = re.findall(
        r"^\s*(?:[-*]\s*)?\*{0,2}(Pass|Recirculate)\b",
        body, re.I | re.M)
    if len(values) != 1:
        return None, [finding(
            "G3.verdict_count",
            "G3 point-back: Verdict section must contain exactly one "
            "Pass or Recirculate verdict",
            owner="point-back.md#Verdict",
            expected="exactly one Pass or Recirculate",
            actual=str(len(values)),
            repair="State exactly one Pass or Recirculate verdict",
        )]
    return values[0].casefold(), []


def check_pointback(text: str, expected_l6: int) -> list[Finding]:
    errs: list[Finding] = []
    pb_findings = _findings(text)
    verdict, verdict_errs = _verdict(text)
    errs += verdict_errs
    is_pass = verdict == "pass"
    errs += _check_evidence(text, expected_l6, is_pass)
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

        severity = pb_finding["severity"][0] if pb_finding["severity"] else ""
        if re.search(r"(?<!non-)\bblocking\b", severity, re.I):
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
