"""G6 soft warnings (ADR-0023): manifest-ts and superseded-artifact signals.

Not hard gates — printed as WARN and never flip a structurally valid run to
exit 1. Shares the ledger/manifest helpers with the G6 gate
(``g6_evidence.py``); kept separate so the hard-gate module stays focused.
"""
from __future__ import annotations

from pathlib import Path

from design_playbook.scripts._diagnostics import Finding, finding
from design_playbook.scripts.g6_records import (
    latest_by_instant,
    ledger_observed,
    manifest_entries,
)
from design_playbook.scripts.stages import EVIDENCE_PREFIX


def check_manifest_ts_warnings(
        evidence_dir: Path | None, *, entries: list[dict] | None = None
) -> list[Finding]:
    """Soft signal: all manifest rows share one ``ts`` (likely batch bind).

    Not a hard gate — root fix is orchestrator per-capture append (SKILL step 8).
    Printed as WARN; does not fail the run. Fires only when ≥2 entries exist and
    every non-empty ``ts`` value is identical (including when some rows omit ts
    only if at least two share the same non-empty value and no other ts exists)
    AND at least one criterion carries multiple rows — a shared ts only weakens
    latest-by-ts when a criterion actually has competing entries (2026-09-22
    rerun D-4: one row per criterion is zero real ambiguity, so stay quiet).
    """
    if evidence_dir is None or not evidence_dir.is_dir():
        return []
    entries = entries if entries is not None else manifest_entries(evidence_dir)
    if len(entries) < 2:
        return []
    ts_vals = [
        e.get("ts") for e in entries
        if isinstance(e.get("ts"), str) and e.get("ts").strip()
    ]
    if len(ts_vals) < 2:
        return []
    if len(set(ts_vals)) != 1:
        return []
    criterion_counts: dict[str, int] = {}
    for entry in entries:
        criterion = entry.get("criterion")
        if isinstance(criterion, str) and criterion:
            criterion_counts[criterion] = criterion_counts.get(criterion, 0) + 1
    if not any(count > 1 for count in criterion_counts.values()):
        return []
    return [finding(
        "G6.batch_ts",
        "G6 evidence: all manifest entries share one ts "
        f"({ts_vals[0]}) with multiple rows on the same criterion; prefer "
        "per-capture append (batch bind weakens multi-entry latest-by-ts)",
        owner="evidence/manifest.jsonl",
        expected="distinct per-capture timestamps",
        actual=ts_vals[0],
        repair="Append manifest entries at capture time, not in batch",
        severity="warning",
    )]


def check_superseded_ledger_warnings(
        pointback_text: str,
        evidence_dir: Path | None, *,
        observed_rows: list[tuple[str, str]] | None = None,
        entries: list[dict] | None = None) -> list[Finding]:
    """Warn when a ledger cites an artifact that is not the latest binding."""
    if evidence_dir is None or not evidence_dir.is_dir():
        return []
    entries = entries if entries is not None else manifest_entries(evidence_dir)
    if not entries:
        return []
    # Latest artifact per criterion by ts instant (mixed Z / +08:00 stamps
    # must compare by capture time, not by string order). An unusable ts has
    # no latest to name: stay quiet here - the hard gate reports malformed
    # binding timestamps as G6.binding_conflict.
    latest_by_crit: dict[str, str] = {}
    for crit in {e.get("criterion") for e in entries if isinstance(e.get("criterion"), str)}:
        candidates = [
            e for e in entries
            if e.get("criterion") == crit and isinstance(e.get("artifact"), str)
        ]
        if not candidates:
            continue
        latest = latest_by_instant(candidates)
        if latest is None:
            continue
        latest_by_crit[crit] = latest["artifact"]

    warns: list[Finding] = []
    rows = observed_rows if observed_rows is not None else ledger_observed(pointback_text)
    for criterion, observed in rows:
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


def _ledger_has_evidence_binding(
        pointback_text: str,
        observed_rows: list[tuple[str, str]] | None = None) -> bool:
    rows = observed_rows if observed_rows is not None else ledger_observed(pointback_text)
    for _criterion, observed in rows:
        # Match check_evidence: case-insensitive evidence/ prefix (LOW-3).
        if observed.casefold().startswith(EVIDENCE_PREFIX):
            return True
    return False
