"""G9 shaping-exit gate (vNext S1, shaping-prototype S0-S6 / loop G9 row).

Machine-checkable face of the S6 exit conditions when a shaping session
exists (vnext-prototype G9 row, decision Q8=A — independent gate module
orchestrated by ``validate_run.py`` like g1/g5/g6):

- shaping-log.jsonl events parse and use the closed event enum
- a projection record exists (decision id <-> contract field <-> spec
  section mapping rows inside ``projected`` events)
- derived queue.json is consistent with a re-derivation from the log
- when contract paths are supplied: open fields = 0 and every assumed field
  acknowledged, reusing the bind-first snapshot (blockers empty)

Condition c of S6 ("L1+L6 traceable to decided or acknowledged-assumed")
stays protocol-side; G1/G7 cleanliness is checked by the existing gates the
same orchestrator already runs.
"""
from __future__ import annotations

import json
from pathlib import Path

from design_playbook.scripts._diagnostics import Finding, finding
from design_playbook.scripts.shaping_log import (
    SHAPING_LOG,
    SHAPING_QUEUE,
    derive_queue,
    parse_shaping_log,
)


def _projection_findings(events: list[dict]) -> list[Finding]:
    findings: list[Finding] = []
    projected = [
        event for event in events if event.get("event") == "projected"
    ]
    if not projected:
        findings.append(finding(
            "G9.missing_projection",
            "G9 shaping: no projected event in the shaping log "
            "(S5 projection record required before exit)",
            owner=SHAPING_LOG,
            expected=">=1 projected event with decision/field/spec mappings",
            actual="none",
            repair="Record the S5 projection (promote_fields -> "
                   "append_decision -> apply_decisions -> spec -> bind_first)",
        ))
        return findings
    for index, event in enumerate(projected, 1):
        mappings = event.get("mappings")
        if not isinstance(mappings, list) or not mappings:
            findings.append(finding(
                "G9.missing_projection",
                f"G9 shaping: projected event {index} has no mapping rows",
                owner=SHAPING_LOG,
                expected="mappings: [{decision, field, spec_section}, ...]",
                actual="missing or empty",
                repair="Record decision id <-> contract field <-> spec "
                       "section for every projected value",
            ))
            continue
        for row in mappings:
            if not isinstance(row, dict) or not (
                isinstance(row.get("decision"), str) and row.get("decision")
                and isinstance(row.get("field"), str) and row.get("field")
                and isinstance(row.get("spec_section"), str)
                and row.get("spec_section")
            ):
                findings.append(finding(
                    "G9.bad_projection_mapping",
                    f"G9 shaping: projected event {index} mapping row is "
                    "not decision/field/spec_section shaped",
                    owner=SHAPING_LOG,
                    expected="{decision, field, spec_section} per row",
                    actual=repr(row)[:120],
                    repair="Complete the three-part mapping for each "
                           "projected value",
                ))
    return findings


def _queue_findings(shaping_dir: Path, events: list[dict]) -> list[Finding]:
    queue_path = shaping_dir / "queue.json"
    if not queue_path.is_file():
        return [finding(
            "G9.missing_queue",
            "G9 shaping: queue.json missing (derived state must sit beside "
            "the log)",
            owner=SHAPING_QUEUE,
            expected="derived queue.json",
            actual="missing",
            repair="Rebuild queue.json from shaping-log.jsonl",
        )]
    try:
        queue = json.loads(queue_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [finding(
            "G9.missing_queue",
            f"G9 shaping: queue.json is not valid JSON: {exc}",
            owner=SHAPING_QUEUE,
            expected="valid JSON object",
            actual=str(exc),
            repair="Rebuild queue.json from shaping-log.jsonl",
        )]
    derived = derive_queue(events)
    if queue != derived:
        return [finding(
            "G9.queue_drift",
            "G9 shaping: queue.json does not match a re-derivation from "
            "shaping-log.jsonl",
            owner=SHAPING_QUEUE,
            expected="queue equal to derive_queue(log)",
            actual="drifted derived state",
            repair="Rebuild queue.json from the append-only log",
        )]
    return []


def _contract_findings(
        project_dir: Path | None, run_dir: Path | None) -> list[Finding]:
    """S6 a/b machine face: open=0 and all assumed acked (bind snapshot)."""
    if project_dir is None or run_dir is None:
        return []
    from design_playbook.scripts.contract_v1 import BIND_SNAPSHOT_FILENAME

    snapshot_path = run_dir / BIND_SNAPSHOT_FILENAME
    if not snapshot_path.is_file():
        return [finding(
            "G9.missing_binding",
            "G9 shaping: bind-first snapshot missing for a run with a "
            "shaping session",
            owner=str(snapshot_path),
            expected="contract-bind.json from bind_first",
            actual="missing",
            repair="Run bind-first with acknowledgements for every assumed "
                   "field before exiting the session",
        )]
    try:
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [finding(
            "G9.missing_binding",
            f"G9 shaping: bind snapshot unreadable: {exc}",
            owner=BIND_SNAPSHOT_FILENAME,
            expected="valid bind-first snapshot",
            actual=str(exc),
            repair="Re-run bind-first",
        )]
    if snapshot.get("ok") is not True:
        blockers = snapshot.get("blockers")
        detail = (
            "; ".join(blockers) if isinstance(blockers, list) else repr(blockers)
        )
        return [finding(
            "G9.open_or_unacked",
            "G9 shaping: S6 exit requires open=0 and every assumed field "
            f"acknowledged this run; bind snapshot blockers: {detail}",
            owner=BIND_SNAPSHOT_FILENAME,
            expected="bind_first ok (no open fields, all assumed acked)",
            actual=detail[:200],
            repair="Resolve open fields (CP-D) and acknowledge every "
                   "assumed field (CP-E), then re-bind",
        )]
    return []


def check_g9(
        shaping_dir: Path,
        *,
        project_dir: Path | None = None,
        run_dir: Path | None = None,
        log_text: str | None = None) -> list[Finding]:
    """Return G9 findings for a shaping session dir (empty = pass)."""
    from design_playbook.scripts.shaping_log import ShapingLogError

    if log_text is None:
        log_path = shaping_dir / "shaping-log.jsonl"
        if not log_path.is_file():
            return [finding(
                "G9.missing_log",
                "G9 shaping: shaping session exists without shaping-log.jsonl",
                owner=SHAPING_LOG,
                expected="append-only shaping event log",
                actual="missing",
                repair="Write shaping events to shaping/shaping-log.jsonl",
            )]
        log_text = log_path.read_text(encoding="utf-8")

    try:
        events = parse_shaping_log(log_text)
    except ShapingLogError as exc:
        return [finding(
            "G9.invalid_event",
            f"G9 shaping: {exc}",
            owner=SHAPING_LOG,
            expected="events from the closed shaping event enum",
            actual=str(exc),
            repair="Use asked/answered/assumption_staged/confirm_presented/"
                   "item_confirmed/item_rejected/item_revised/projected/"
                   "suspended/resumed/superseded_by/archived",
        )]
    if not events:
        return [finding(
            "G9.missing_log",
            "G9 shaping: shaping-log.jsonl is empty",
            owner=SHAPING_LOG,
            expected=">=1 shaping event",
            actual="0 events",
            repair="Record session events (S0 intake onward)",
        )]

    findings: list[Finding] = []
    findings += _projection_findings(events)
    findings += _queue_findings(shaping_dir, events)
    findings += _contract_findings(project_dir, run_dir)
    return findings


def main(argv: list[str]) -> int:
    import sys

    if len(argv) not in (2, 4):
        print(
            "Usage: g9_shaping.py <shaping_dir> [project_dir run_dir]",
            file=sys.stderr,
        )
        return 2
    findings = check_g9(
        Path(argv[1]),
        project_dir=Path(argv[2]) if len(argv) == 4 else None,
        run_dir=Path(argv[3]) if len(argv) == 4 else None,
    )
    if not findings:
        print("G9 OK: shaping session satisfies the exit gate")
        return 0
    print("G9 INVALID:")
    for item in findings:
        print(f"  FAIL  {item.message}")
    return 1


if __name__ == "__main__":
    import sys

    sys.exit(main(sys.argv))
