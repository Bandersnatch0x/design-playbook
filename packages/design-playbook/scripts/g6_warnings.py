"""G6 soft warnings (ADR-0023): manifest-ts and superseded-artifact signals.

Not hard gates — printed as WARN and never flip a structurally valid run to
exit 1. Shares the ledger/manifest helpers with the G6 gate
(``g6_evidence.py``); kept separate so the hard-gate module stays focused.
"""
from __future__ import annotations

from pathlib import Path

from design_playbook.scripts._diagnostics import Finding, finding
from design_playbook.scripts.stages import EVIDENCE_PREFIX
from design_playbook.scripts.g6_evidence import _ledger_observed, _manifest_entries


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
