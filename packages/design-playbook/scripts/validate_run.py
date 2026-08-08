#!/usr/bin/env python3
"""Deterministic seam over Design I/O run artifacts. No dependencies.

Gates the run-level controls that the skills also declare in prose:
  G1 success shape       - L1-L6 present; every L6 item is Given/When/Then
  G2 evidence/point-back - every L6 item has one complete evidence row and
                           every finding has issue/source/fix/severity
  G3 verdict earned      - one explicit verdict; Pass requires all evidence to
                           pass and every blocking finding to have a closure
  G4 recirculation bound - closure coverage prevents blockers being dropped;
                           the two-cycle stop policy remains agent-enforced
  G5 preview confirm     - conditional: if preview occurred, require a
                           confirmed record whose report_ref matches the
                           current decision report (when provided)
  G6 evidence binding    - conditional: if a ledger `observed` references an
                           `evidence/` artifact, require the artifact to exist
                           and a manifest entry to bind it to the matching
                           L6.<n> (multi-entry: latest wins)

Reads plain Markdown, so it is host-neutral: it accepts artifacts produced by
any agent (Claude Code, Codex) that follow the declared shape.

Usage:
  validate_run.py <spec.md> <point-back.md>
      [--preview-dir <path>] [--decision-report <path>]
      [--evidence-dir <path>] [--run-root <path>]
      [--require-preview] [--require-evidence] [--strict]
      [--format text|json]
Exit 0 + "RUN OK"; exit 1 + one line per artifact violation; exit 2 on usage
or artifact I/O errors. JSON mode projects the same findings as a list.

Strict quality mode (opt-in):
  --require-preview   fail when preview did not occur (G5 must fire)
  --require-evidence  fail when no evidence/ binding is present (G6 must fire)
  --strict            shorthand for both require flags
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

# Structured diagnostics (vNext ticket 02): one Finding model feeds text and
# JSON projections. Rule IDs stay stable; text keeps historical messages.
from _diagnostics import (
    OUTPUT_FORMATS,
    Finding,
    finding,
    render_json,
    render_text,
    usage_finding,
)

# Preview integrity rules live with the bundled Preview runtime. This scripts/
# directory is not a package, so the read adapter adds that sibling runtime
# exactly once; replacing sys.path adapters is Candidate 5, not this deepening.
_PREVIEW_RUNTIME_DIR = Path(__file__).resolve().parent.parent / "mcp" / "preview"
if str(_PREVIEW_RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(_PREVIEW_RUNTIME_DIR))
from integrity import ConfirmRecord, PreviewSnapshot, inspect_preview  # noqa: E402

try:
    from g7_contract_drift import check_g7 as check_g7
except ImportError:  # pragma: no cover - optional until package scripts co-locate
    check_g7 = None  # type: ignore[assignment]

SPEC_LAYERS = ["L1", "L2", "L3", "L4", "L5", "L6"]
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


def _l6_body(text: str) -> str:
    parts = re.split(r"^#+\s*L6\b", text, maxsplit=1, flags=re.M)
    if len(parts) == 1:
        return ""
    return re.split(r"^#+\s+", parts[1], maxsplit=1, flags=re.M)[0]


def _l6_items(text: str) -> list[str]:
    return [match.group(1).strip() for match in re.finditer(
        r"^(?:[-*]|\d+[.)])\s+(.*?)(?=^(?:[-*]|\d+[.)])\s+|\Z)",
        _l6_body(text),
        re.M | re.S,
    )]


def check_spec(text: str) -> list[Finding]:
    errs: list[Finding] = []
    for layer in SPEC_LAYERS:
        # heading like "## L6 验收标准" or "## L6"
        if not re.search(rf"^#+\s*{layer}\b", text, re.M):
            errs.append(finding(
                "G1.missing_layer",
                f"G1 spec: missing {layer}",
                owner="spec.md",
                expected=f"heading for {layer}",
                actual="missing",
                repair=f"Add a top-level {layer} section to the spec",
            ))
    items = _l6_items(text)
    if not items:
        errs.append(finding(
            "G1.no_criteria",
            "G1 spec: L6 has no top-level acceptance criteria",
            owner="spec.md#L6",
            expected=">=1 top-level L6 criterion",
            actual="0",
            repair="Add Given/When/Then acceptance criteria under L6",
        ))
    for number, item in enumerate(items, 1):
        positions = {
            keyword: re.search(rf"\b{keyword}\b", item, re.I)
            for keyword in ("Given", "When", "Then")
        }
        missing = [name for name, match in positions.items() if not match]
        if missing:
            errs.append(finding(
                "G1.missing_gwt",
                f"G1 spec: L6.{number} missing {', '.join(missing)}",
                owner=f"spec.md#L6.{number}",
                expected="Given, When, Then present",
                actual=f"missing {', '.join(missing)}",
                repair=f"Complete Given/When/Then for L6.{number}",
            ))
            continue
        if not (positions["Given"].start() < positions["When"].start() <
                positions["Then"].start()):
            errs.append(finding(
                "G1.gwt_order",
                f"G1 spec: L6.{number} must order Given -> When -> Then",
                owner=f"spec.md#L6.{number}",
                expected="Given -> When -> Then order",
                actual="out of order",
                repair=f"Reorder keywords for L6.{number}",
            ))
    return errs


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


def preview_occurred(preview_dir: Path | None) -> bool:
    """Project Preview integrity occurrence for G5/strict-mode callers."""
    return preview_dir is not None and inspect_preview(preview_dir).occurred


def _resolve_report_ref(
        ref: str, preview_dir: Path,
        decision_report: Path | None) -> Path | None:
    raw = Path(ref)
    candidates: list[Path] = []
    if raw.is_absolute():
        candidates.append(raw)
    else:
        # run root = parent of preview/
        candidates.append(preview_dir.parent / raw)
        candidates.append(preview_dir / raw)
        if decision_report is not None:
            candidates.append(decision_report.parent / raw)
        candidates.append(Path.cwd() / raw)
    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate.resolve()
        except OSError:
            continue
    return None


def _g5_no_valid_reason(current: tuple[ConfirmRecord, ...]) -> list[Finding]:
    """Explain invalid current confirms without owning integrity rules."""
    confirmed = [
        record for record in current
        if isinstance(record.data, dict) and record.data.get("confirmed") is True
    ]
    if not confirmed:
        return [finding(
            "G5.no_confirmed",
            "G5 preview: preview occurred but no confirm-round-*.json with "
            "confirmed=true",
            owner="preview/",
            expected="confirm-round-*.json with confirmed=true",
            actual="no valid confirmed record in current round",
            repair="Complete preview* HITL and write a confirmed confirm-round",
        )]
    record = confirmed[0]
    data = record.data
    assert isinstance(data, dict)
    if data.get("floor_pass") is not True:
        reason = data.get("floor_failure") or "no floor_pass=true"
        return [finding(
            "G5.floor_fail",
            f"G5 preview: confirmed record {record.path.name} failed feedback floor: "
            f"{reason}",
            owner=f"preview/{record.path.name}",
            expected="floor_pass=true on confirmed record",
            actual=str(reason),
            repair="Revise with substantive feedback and re-confirm",
        )]
    if data.get("aborted") is True:
        return [finding(
            "G5.aborted",
            f"G5 preview: confirmed record {record.path.name} is aborted; an aborted "
            "round cannot satisfy the preview gate",
            owner=f"preview/{record.path.name}",
            expected="non-aborted confirmed record",
            actual="aborted=true",
            repair="Start a new preview round and confirm it",
        )]
    return [finding(
        "G5.invalid_confirm",
        f"G5 preview: confirmed record {record.path.name} is not a valid confirm",
        owner=f"preview/{record.path.name}",
        expected="confirmed=true and floor_pass=true",
        actual=record.path.name,
        repair="Rewrite confirm-round with a valid confirm payload",
    )]


def _g5_fact_findings(snapshot: PreviewSnapshot) -> list[Finding]:
    """Project host-neutral Preview integrity facts into G5 diagnostics."""
    for fact in snapshot.facts:
        owner = f"preview/{fact.path.name}" if fact.path is not None else "preview/"
        if fact.code == "preview_unreadable":
            return [finding(
                "G5.preview_unreadable",
                f"G5 preview: cannot read preview dir: {fact.detail}",
                owner="preview/",
                expected="readable preview directory",
                actual=fact.detail,
                repair="Fix preview directory permissions or path",
            )]
        if fact.code == "invalid_confirm_record":
            return [finding(
                "G5.invalid_confirm_record",
                f"G5 preview: {fact.detail}",
                owner=owner,
                expected="valid confirm-round JSON object",
                actual=fact.detail,
                repair="Rewrite the confirm record as valid JSON",
            )]
        if fact.code == "confirm_not_object":
            return [finding(
                "G5.confirm_not_object",
                f"G5 preview: {fact.detail}",
                owner=owner,
                expected="JSON object",
                actual=fact.actual,
                repair="Rewrite confirm-round as a JSON object",
            )]
        if fact.code == "missing_hash":
            return [finding(
                "G5.missing_hash",
                "G5 preview: confirmed record missing prototype_html_hash "
                "(pre-0.4.4 record or hand-written — re-run preview*)",
                owner="preview/",
                expected="prototype_html_hash on confirmed record",
                actual="missing",
                repair="Re-run preview* so the adapter writes the hash",
            )]
        if fact.code == "missing_prototype":
            return [finding(
                "G5.missing_prototype",
                "G5 preview: confirmed record carries prototype_html_hash but "
                "its prototype html is missing",
                owner="preview/",
                expected="preview/round-<n>.html on disk",
                actual="prototype html missing or outside preview/",
                repair="Restore the prototype html or re-run preview*",
            )]
        if fact.code == "hash_mismatch":
            round_name = (
                f"round-{snapshot.current_round}.html"
                if snapshot.current_round is not None else "preview/"
            )
            return [finding(
                "G5.hash_mismatch",
                "G5 preview: confirmed record prototype_html_hash mismatch "
                "(prototype altered after confirm)",
                owner=round_name,
                expected=fact.expected,
                actual=fact.actual,
                repair="Re-confirm after prototype changes, or restore the confirmed html",
            )]
    return []


def check_preview(
        preview_dir: Path | None,
        decision_report: Path | None,
        snapshot: PreviewSnapshot | None = None) -> list[Finding]:
    """G5 conditional gate projected from one Preview integrity snapshot."""
    if preview_dir is None:
        return []
    snapshot = snapshot or inspect_preview(preview_dir)
    if not snapshot.occurred:
        return []

    fact_findings = _g5_fact_findings(snapshot)
    if fact_findings and fact_findings[0].rule_id in {
        "G5.preview_unreadable",
        "G5.invalid_confirm_record",
        "G5.confirm_not_object",
    }:
        return fact_findings

    current = snapshot.current_confirms
    latest = snapshot.current_round
    if not current:
        if latest is not None:
            return [finding(
                "G5.stale_round",
                f"G5 preview: latest round {latest} has no "
                f"confirm-round-{latest}.json (stale confirmation; only an "
                f"older round may be confirmed)",
                owner="preview/",
                expected=f"confirm-round-{latest}.json",
                actual="stale older confirm only",
                repair=f"Confirm the latest round ({latest})",
            )]
        return [finding(
            "G5.no_confirmed",
            "G5 preview: preview occurred but no confirm-round-*.json with "
            "confirmed=true",
            owner="preview/",
            expected="confirm-round-*.json with confirmed=true",
            actual="none",
            repair="Complete preview* HITL and write a confirmed confirm-round",
        )]

    true_confirms = tuple(record for record in current if record.valid)
    if not true_confirms:
        return _g5_no_valid_reason(current)
    if fact_findings:
        return fact_findings

    wanted: Path | None = None
    if decision_report is not None:
        try:
            wanted = decision_report.resolve()
        except OSError as exc:
            return [finding(
                "G5.decision_report_unresolvable",
                f"G5 preview: cannot resolve --decision-report: {exc}",
                owner="--decision-report",
                expected="resolvable decision report path",
                actual=str(exc),
                repair="Pass a resolvable --decision-report path",
            )]
        if not wanted.is_file():
            return [finding(
                "G5.decision_report_missing",
                f"G5 preview: --decision-report does not exist: "
                f"{decision_report}",
                owner="--decision-report",
                expected="existing decision report file",
                actual=str(decision_report),
                repair="Create the decision report or fix the path",
            )]

    for record in true_confirms:
        data = record.data
        assert isinstance(data, dict)
        ref = data.get("report_ref")
        if not isinstance(ref, str) or not ref.strip():
            continue
        resolved = _resolve_report_ref(ref.strip(), preview_dir, decision_report)
        if resolved is None:
            continue
        if wanted is None or resolved == wanted:
            return []

    if wanted is not None:
        return [finding(
            "G5.report_ref_mismatch",
            "G5 preview: no confirmed record whose report_ref matches "
            f"--decision-report ({wanted.name})",
            owner="preview/",
            expected=f"report_ref resolving to {wanted.name}",
            actual="no matching confirmed record",
            repair="Confirm against the current decision report",
        )]
    return [finding(
        "G5.report_ref_unresolved",
        "G5 preview: confirmed record report_ref does not resolve to an "
        "existing decision report",
        owner="preview/",
        expected="report_ref to an existing decision report",
        actual="unresolved report_ref",
        repair="Fix report_ref or restore the decision report file",
    )]


EVIDENCE_PREFIX = "evidence/"


def _ledger_observed(text: str) -> list[tuple[str, str]]:
    """Return (criterion, observed) pairs for each evidence row.

    The G6 evidence path is the leading token of the observed line; trailing
    commentary after whitespace, a (full/half-width) paren, or a
    (full/half-width) comma / colon is tolerated so authors can annotate
    ``evidence/`` rows without a false-positive G6 fail (issue 03). Free-text
    observed is unaffected — G6 only checks evidence/ rows, and a leading
    token starting with ``evidence/`` never appears in free text.

    Keep the tolerated separators in sync with skills/ui-evaluator/SKILL.md
    (which teaches authors what punctuation may follow the artifact path).
    """
    pairs: list[tuple[str, str]] = []
    for block in re.split(r"\n\s*\n", text):
        crit = re.search(r"^criterion:\s*(\S+)", block, re.I | re.M)
        obs = re.search(r"^observed:\s*(.+)$", block, re.I | re.M)
        if crit and obs:
            raw = obs.group(1).strip()
            lead = re.match(r"[^\s（(,，:：]+", raw)
            observed = lead.group(0) if lead else raw
            pairs.append((crit.group(1).strip(), observed))
    return pairs


def _manifest_entries(evidence_dir: Path) -> list[dict]:
    """Read .scratch/<run>/evidence/manifest.jsonl; one dict per non-empty line."""
    path = evidence_dir / "manifest.jsonl"
    if not path.is_file():
        return []
    entries: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            entries.append(data)
    return entries


def check_evidence(
        pointback_text: str,
        expected_l6: int,
        evidence_dir: Path | None,
        run_root: Path | None) -> list[Finding]:
    """G6 conditional evidence-binding gate.

    Triggers only when a ledger ``observed`` references an ``evidence/``
    artifact. For each such row, the artifact must exist and a manifest entry
    must bind it to the matching L6.<n> (multi-entry: latest by ts wins).
    Weak/conditional: rows with free-text observed are not checked; pass rows
    are not required to reference evidence.
    """
    if evidence_dir is None or not evidence_dir.is_dir():
        return []
    root = run_root if run_root is not None else evidence_dir.parent
    entries = _manifest_entries(evidence_dir)
    valid_criterion_ids = {f"L6.{n}" for n in range(1, expected_l6 + 1)}
    evidence_root = (root / "evidence").resolve()

    errs: list[Finding] = []
    for criterion, observed in _ledger_observed(pointback_text):
        # LOW-3: case-insensitive prefix. The write boundary treats paths
        # case-insensitively on case-insensitive filesystems (Windows), so
        # ``EVIDENCE/<x>`` lands in the evidence/ subtree on disk; the read
        # side must match the same way or uppercase rows skip G6 entirely.
        # After the casefold match, rewrite the leading segment to the
        # canonical ``evidence/`` so path resolution stays under that subtree
        # on case-*sensitive* filesystems (Linux CI) too — otherwise
        # ``root / "EVIDENCE/…"`` resolves as a sibling of ``evidence/`` and
        # the containment check spuriously reports "escapes" instead of the
        # intended missing/bound diagnostic.
        if not observed.casefold().startswith(EVIDENCE_PREFIX):
            continue  # free-text observation; G6 does not apply
        leaf = observed[len(EVIDENCE_PREFIX):]
        canonical = EVIDENCE_PREFIX + leaf
        # Containment (issue 04 / G6): the observed path must resolve *inside*
        # the evidence/ subtree. Reject any ".." segment, absolute paths, and
        # post-resolve escapes (e.g. ``evidence/../spec.md`` -> run root,
        # which under the new Codex manifest could overwrite spec / source).
        observed_path = Path(canonical)
        if observed_path.is_absolute() or ".." in observed_path.parts:
            errs.append(finding(
                "G6.escape",
                f"G6 evidence: {criterion} observed escapes evidence/ "
                f"subtree: {observed}",
                owner=f"point-back.md#{criterion}",
                expected="observed path inside evidence/",
                actual=observed,
                repair="Point observed at an artifact under evidence/",
            ))
            continue
        try:
            resolved = (root / canonical).resolve()
        except OSError:
            errs.append(finding(
                "G6.escape",
                f"G6 evidence: {criterion} observed escapes evidence/ "
                f"subtree: {observed}",
                owner=f"point-back.md#{criterion}",
                expected="observed path inside evidence/",
                actual=observed,
                repair="Point observed at an artifact under evidence/",
            ))
            continue
        try:
            resolved.relative_to(evidence_root)
        except ValueError:
            errs.append(finding(
                "G6.escape",
                f"G6 evidence: {criterion} observed escapes evidence/ "
                f"subtree: {observed}",
                owner=f"point-back.md#{criterion}",
                expected="observed path inside evidence/",
                actual=observed,
                repair="Point observed at an artifact under evidence/",
            ))
            continue
        # M6: defence in depth — mirror evidence/server.py
        # _resolve_artifact_path. ``Path.resolve`` and ``os.path.realpath``
        # can disagree on symlink chains across platforms, so a symlink under
        # evidence/ that resolves outside must also be rejected on the read
        # side (the write side already rejects it).
        try:
            Path(os.path.realpath(resolved)).relative_to(
                os.path.realpath(evidence_root))
        except ValueError:
            errs.append(finding(
                "G6.escape",
                f"G6 evidence: {criterion} observed escapes evidence/ "
                f"subtree: {observed}",
                owner=f"point-back.md#{criterion}",
                expected="observed path inside evidence/",
                actual=observed,
                repair="Point observed at an artifact under evidence/",
            ))
            continue
        if not resolved.is_file():
            errs.append(finding(
                "G6.artifact_missing",
                f"G6 evidence: {criterion} artifact missing: {observed}",
                owner=f"evidence/{leaf}",
                expected="artifact file on disk",
                actual="missing",
                repair=f"Capture or restore {observed}",
            ))
            continue
        # ledger observed is run-root-relative ("evidence/<name>"); manifest
        # artifact is evidence/-relative ("<name>", no prefix) per ticket 01.
        # Normalise the ledger leaf and compare to the manifest artifact
        # exactly; require the manifest criterion to match the ledger row.
        bound: list[dict] = []
        for entry in entries:
            if entry.get("criterion") != criterion:
                continue
            art = entry.get("artifact")
            if isinstance(art, str) and art == leaf:
                bound.append(entry)
        if not bound:
            # distinguish unknown-criterion (manifest binds a criterion not in
            # spec) from no-binding (manifest criterion != ledger criterion)
            unknown = [
                e for e in entries
                if isinstance(e.get("criterion"), str)
                and e["criterion"] not in valid_criterion_ids
                and isinstance(e.get("artifact"), str)
                and e["artifact"] == leaf
            ]
            if unknown:
                crit = unknown[0].get("criterion")
                errs.append(finding(
                    "G6.unknown_criterion",
                    f"G6 evidence: manifest binds unknown criterion {crit}",
                    owner="evidence/manifest.jsonl",
                    expected=f"criterion in L6.1..L6.{expected_l6}",
                    actual=str(crit),
                    repair="Bind the artifact to a declared L6 criterion",
                ))
            else:
                errs.append(finding(
                    "G6.no_binding",
                    f"G6 evidence: {criterion} no manifest entry binding "
                    f"{observed}",
                    owner="evidence/manifest.jsonl",
                    expected=f"manifest entry for {criterion} -> {leaf}",
                    actual="no binding",
                    repair="Append a manifest line binding criterion and artifact",
                ))
            continue
        latest = max(bound, key=lambda m: m.get("ts", ""))
        if latest.get("criterion") not in valid_criterion_ids:
            errs.append(finding(
                "G6.unknown_criterion",
                f"G6 evidence: manifest binds unknown criterion "
                f"{latest.get('criterion')}",
                owner="evidence/manifest.jsonl",
                expected=f"criterion in L6.1..L6.{expected_l6}",
                actual=str(latest.get("criterion")),
                repair="Bind the artifact to a declared L6 criterion",
            ))
            continue
        # Capture contract v1 (ADR-0018): bound evidence must embed schemaVersion=1
        # plus viewport. Unversioned rows have no compatibility reader — recapture.
        capture = latest.get("capture") if isinstance(latest.get("capture"), dict) else {}
        request = latest.get("request")
        if not isinstance(request, dict):
            request = capture.get("request") if isinstance(capture.get("request"), dict) else {}
        version = None
        if isinstance(request, dict):
            version = request.get("schemaVersion")
        if version is None and isinstance(capture, dict):
            version = capture.get("schemaVersion")
        if version != 1:
            errs.append(finding(
                "G6.capture_schema",
                f"G6 evidence: {criterion} capture missing schemaVersion=1 "
                f"(got {version!r}); recapture with capture contract v1",
                owner="evidence/manifest.jsonl",
                expected="schemaVersion=1 with viewport on the bound entry",
                actual=repr(version),
                repair="Recapture the artifact with execute_capture_plan schemaVersion=1",
            ))
            continue
        viewport = request.get("viewport") if isinstance(request, dict) else None
        if not isinstance(viewport, dict):
            errs.append(finding(
                "G6.capture_viewport",
                f"G6 evidence: {criterion} capture missing viewport snapshot; "
                "recapture with capture contract v1",
                owner="evidence/manifest.jsonl",
                expected="viewport width/height/devicePixelRatio/colorScheme",
                actual="missing",
                repair="Recapture and embed the provider request snapshot",
            ))
            continue
        # artifact exists + bound + capture contract v1 -> valid; result is
        # the evaluator's call, not G6's.
    return errs


def check_manifest_ts_warnings(evidence_dir: Path | None) -> list[Finding]:
    """Soft signal: all manifest rows share one ``ts`` (likely batch bind).

    Not a hard gate — root fix is orchestrator per-capture append (SKILL step 8).
    Printed as WARN; does not fail the run. Fires only when ≥2 entries exist and
    every non-empty ``ts`` value is identical (including when some rows omit ts
    only if at least two share the same non-empty value and no other ts exists).
    """
    if evidence_dir is None or not evidence_dir.is_dir():
        return []
    entries = _manifest_entries(evidence_dir)
    if len(entries) < 2:
        return []
    ts_vals = [
        e.get("ts") for e in entries
        if isinstance(e.get("ts"), str) and e.get("ts").strip()
    ]
    if len(ts_vals) < 2:
        return []
    if len(set(ts_vals)) == 1:
        return [finding(
            "G6.batch_ts",
            "G6 evidence: all manifest entries share one ts "
            f"({ts_vals[0]}); prefer per-capture append "
            "(batch bind weakens multi-entry latest-by-ts)",
            owner="evidence/manifest.jsonl",
            expected="distinct per-capture timestamps",
            actual=ts_vals[0],
            repair="Append manifest entries at capture time, not in batch",
            severity="warning",
        )]
    return []


def check_superseded_ledger_warnings(
        pointback_text: str,
        evidence_dir: Path | None) -> list[Finding]:
    """Warn when a ledger cites an artifact that is not the latest binding."""
    if evidence_dir is None or not evidence_dir.is_dir():
        return []
    entries = _manifest_entries(evidence_dir)
    if not entries:
        return []
    # Latest artifact per criterion by ts.
    latest_by_crit: dict[str, str] = {}
    for crit in {e.get("criterion") for e in entries if isinstance(e.get("criterion"), str)}:
        candidates = [
            e for e in entries
            if e.get("criterion") == crit and isinstance(e.get("artifact"), str)
        ]
        if not candidates:
            continue
        latest = max(candidates, key=lambda m: m.get("ts", ""))
        latest_by_crit[crit] = latest["artifact"]

    warns: list[Finding] = []
    for criterion, observed in _ledger_observed(pointback_text):
        if not observed.casefold().startswith(EVIDENCE_PREFIX):
            continue
        leaf = observed[len(EVIDENCE_PREFIX):]
        current = latest_by_crit.get(criterion)
        if current and leaf != current:
            warns.append(finding(
                "G6.superseded_artifact",
                f"G6 evidence: {criterion} ledger cites {observed} but latest "
                f"manifest binding is evidence/{current}",
                owner=f"point-back.md#{criterion}",
                expected=f"evidence/{current}",
                actual=observed,
                repair="Update the ledger to the current artifact or recapture",
                severity="warning",
            ))
    return warns


def _ledger_has_evidence_binding(pointback_text: str) -> bool:
    for _criterion, observed in _ledger_observed(pointback_text):
        # Match check_evidence: case-insensitive evidence/ prefix (LOW-3).
        if observed.casefold().startswith(EVIDENCE_PREFIX):
            return True
    return False


def run(
        spec_path: str,
        pb_path: str,
        preview_dir: str | None = None,
        decision_report: str | None = None,
        evidence_dir: str | None = None,
        run_root: str | None = None,
        require_preview: bool = False,
        require_evidence: bool = False,
        contract_project: str | None = None,
        contract_run: str | None = None) -> tuple[list[Finding], list[Finding]]:
    """Return ``(errors, warnings)``. Errors fail the run; warnings do not."""
    errs: list[Finding] = []
    warns: list[Finding] = []
    spec_text = Path(spec_path).read_text(encoding="utf-8")
    pointback_text = Path(pb_path).read_text(encoding="utf-8")
    errs += check_spec(spec_text)
    errs += check_pointback(pointback_text, len(_l6_items(spec_text)))
    pd = Path(preview_dir) if preview_dir else None
    preview_snapshot = inspect_preview(pd) if pd is not None else None
    dr = Path(decision_report) if decision_report else None
    if require_preview and (
        preview_snapshot is None or not preview_snapshot.occurred
    ):
        errs.append(finding(
            "G5.require_preview",
            "G5 preview: --require-preview set but preview did not occur "
            "(pass --preview-dir with preview artifacts)",
            owner="--require-preview",
            expected="preview artifacts present",
            actual="preview did not occur",
            repair="Pass --preview-dir with preview artifacts or drop the flag",
        ))
    errs += check_preview(pd, dr, preview_snapshot)
    ed = Path(evidence_dir) if evidence_dir else None
    rr = Path(run_root) if run_root else None
    if require_evidence:
        if ed is None or not ed.is_dir():
            errs.append(finding(
                "G6.require_evidence_dir",
                "G6 evidence: --require-evidence set but --evidence-dir "
                "is missing or not a directory",
                owner="--require-evidence",
                expected="existing --evidence-dir",
                actual="missing or not a directory",
                repair="Pass --evidence-dir to a real evidence directory",
            ))
        elif not _ledger_has_evidence_binding(pointback_text):
            errs.append(finding(
                "G6.require_evidence_binding",
                "G6 evidence: --require-evidence set but no ledger "
                "`observed` references an evidence/ artifact",
                owner="point-back.md#evidence",
                expected="at least one observed: evidence/… row",
                actual="no evidence/ binding",
                repair="Bind at least one L6 criterion to an evidence artifact",
            ))
    errs += check_evidence(pointback_text, len(_l6_items(spec_text)), ed, rr)
    warns += check_manifest_ts_warnings(ed)
    warns += check_superseded_ledger_warnings(pointback_text, ed)
    if contract_project and contract_run:
        if check_g7 is None:
            errs.append(finding(
                "G7.missing_binding",
                "G7 contract: g7_contract_drift module unavailable",
                owner="validate_run.py",
                expected="packaged g7_contract_drift.py",
                actual="import failed",
                repair="Install the design-playbook scripts package intact",
            ))
        else:
            errs += check_g7(Path(contract_project), Path(contract_run))
    return errs, warns


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="validate_run.py",
        description="Deterministic seam over Design I/O run artifacts.",
    )
    parser.add_argument("spec", help="path to spec.md")
    parser.add_argument("point_back", help="path to point-back.md")
    parser.add_argument(
        "--preview-dir",
        default=None,
        help="optional path to .scratch/<run>/preview/ for G5",
    )
    parser.add_argument(
        "--decision-report",
        default=None,
        help="optional path to current decision report for G5 report_ref match",
    )
    parser.add_argument(
        "--evidence-dir",
        default=None,
        help="optional path to .scratch/<run>/evidence/ for G6",
    )
    parser.add_argument(
        "--run-root",
        default=None,
        help="optional run root for resolving evidence/ paths in G6 "
             "(defaults to --evidence-dir parent)",
    )
    parser.add_argument(
        "--require-preview",
        action="store_true",
        help="strict mode: fail when preview did not occur",
    )
    parser.add_argument(
        "--require-evidence",
        action="store_true",
        help="strict mode: fail when no evidence/ binding is present",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="shorthand for --require-preview --require-evidence",
    )
    parser.add_argument(
        "--format",
        default="text",
        dest="output_format",
        help="output projection: text (default) or json",
    )
    parser.add_argument(
        "--contract-project",
        default=None,
        help="optional project dir containing contract.json for G7",
    )
    parser.add_argument(
        "--contract-run",
        default=None,
        help="optional run dir containing contract-bind.json for G7",
    )
    args = parser.parse_args(argv[1:])
    if args.strict:
        args.require_preview = True
        args.require_evidence = True
    return args


def main(argv: list[str]) -> int:
    try:
        args = _parse_args(argv)
    except SystemExit as exc:
        # argparse already printed usage
        code = exc.code if isinstance(exc.code, int) else 2
        return code if code else 2

    fmt = (args.output_format or "text").casefold()
    if fmt not in OUTPUT_FORMATS:
        bad = usage_finding(
            f"unknown --format {args.output_format!r}; expected text or json"
        )
        print(f"RUN ERROR: {bad.message}")
        return 2

    try:
        errs, warns = run(
            args.spec,
            args.point_back,
            preview_dir=args.preview_dir,
            decision_report=args.decision_report,
            evidence_dir=args.evidence_dir,
            run_root=args.run_root,
            require_preview=args.require_preview,
            require_evidence=args.require_evidence,
            contract_project=args.contract_project,
            contract_run=args.contract_run,
        )
    except (OSError, UnicodeError) as exc:
        if fmt == "json":
            print(render_json([finding(
                "USAGE.io_error",
                f"cannot read artifacts: {exc}",
                owner="validate_run.py",
                expected="readable spec and point-back paths",
                actual=str(exc),
                repair="Fix paths or file encodings",
            )], []))
        else:
            print(f"RUN ERROR: cannot read artifacts: {exc}")
        return 2

    if fmt == "json":
        print(render_json(errs, warns), end="")
    else:
        print(render_text(errs, warns), end="")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
