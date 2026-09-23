"""Shared append-only JSONL plumbing for governance logs.

Both governance axes — the rule axis (``rules_governance.py``) and the
component/token promotion axis (``promotion_governance.py``) — keep an
append-only log of one JSON object per line. The *schemas* differ deliberately
(they govern different things); the *plumbing* (parse a line per event, append
one line atomically) is identical and shared here so the two never fork.

Discipline (ADR-0017): lines are only ever appended; existing events are never
rewritten, reordered, or deleted.
"""
from __future__ import annotations

import json


def parse_events(text: str, *, log_label: str = "governance log") -> list[dict]:
    """Parse one JSON event per line. Blank lines are skipped; malformed JSON
    raises ValueError naming the line number; a non-object line is rejected."""
    events: list[dict] = []
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"{log_label} line {number}: bad JSON: {exc}") from exc
        if not isinstance(event, dict):
            raise ValueError(
                f"{log_label} line {number}: event must be a JSON object")
        events.append(event)
    return events


def append_line(path, event: dict) -> None:
    """Append one event as a single JSON line (no validation — the caller's
    schema validator runs first). One line per event; append-only."""
    line = json.dumps(event, ensure_ascii=False)
    with open(path, "a", encoding="utf-8", newline="\n") as handle:
        handle.write(line + "\n")
