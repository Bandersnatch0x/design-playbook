"""G5 preview-confirm gate (ADR-0023).

Conditional: if preview occurred, require a confirmed record whose
``report_ref`` matches the current decision report (when provided). Rules
are projected from the bundled Preview integrity snapshot (C1 / ADR-0004);
this module owns G5 diagnostics, never integrity rules.
"""
from __future__ import annotations

from pathlib import Path

from design_playbook.scripts._diagnostics import Finding, finding
from design_playbook.mcp.preview.integrity import (
    ConfirmRecord,
    PreviewSnapshot,
    inspect_preview,
)


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
