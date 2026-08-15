"""Shaping session artifacts (vNext S1, shaping-prototype 4.1).

Owns the append-only shaping event log format and the derived queue state:

- ``shaping-log.jsonl`` — append-only event log (process authority)
- ``queue.json``        — derived state (rebuildable from the log at any time)

Event enum is closed (shaping-prototype 4.1): ``asked / answered /
assumption_staged / confirm_presented / item_confirmed / item_rejected /
item_revised / projected / suspended / resumed / superseded_by / archived``.
Gate policy lives in ``g9_shaping.py``; this module owns parse + derive.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SHAPING_DIR = "shaping"
SHAPING_LOG = "shaping/shaping-log.jsonl"
SHAPING_QUEUE = "shaping/queue.json"

SHAPING_EVENTS = frozenset({
    "asked",
    "answered",
    "assumption_staged",
    "confirm_presented",
    "item_confirmed",
    "item_rejected",
    "item_revised",
    "projected",
    "suspended",
    "resumed",
    "superseded_by",
    "archived",
})


class ShapingLogError(ValueError):
    """Malformed shaping-log line or derived-state mismatch."""


@dataclass(frozen=True)
class ShapingFacts:
    """One immutable view of a shaping session (parsed events + derived)."""

    events: tuple[dict[str, Any], ...]
    queue: dict[str, Any] = field(default_factory=dict)


def parse_shaping_log(text: str) -> list[dict[str, Any]]:
    """Parse append-only shaping events; raises ShapingLogError on bad shape."""
    events: list[dict[str, Any]] = []
    for line_no, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ShapingLogError(
                f"shaping-log.jsonl:{line_no} invalid JSON: {exc}"
            ) from exc
        if not isinstance(raw, dict):
            raise ShapingLogError(
                f"shaping-log.jsonl:{line_no} event must be a JSON object"
            )
        event = raw.get("event")
        if event not in SHAPING_EVENTS:
            raise ShapingLogError(
                f"shaping-log.jsonl:{line_no} unknown event {event!r}; "
                f"expected one of {sorted(SHAPING_EVENTS)}"
            )
        events.append(raw)
    return events


def load_shaping_facts(run_root: Path) -> ShapingFacts | None:
    """Load shaping facts for a run; None when no session exists."""
    log_path = run_root / SHAPING_LOG
    if not log_path.is_file():
        return None
    events = parse_shaping_log(log_path.read_text(encoding="utf-8"))
    queue: dict[str, Any] = {}
    queue_path = run_root / SHAPING_QUEUE
    if queue_path.is_file():
        try:
            loaded = json.loads(queue_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ShapingLogError(f"queue.json invalid JSON: {exc}") from exc
        if isinstance(loaded, dict):
            queue = loaded
    return ShapingFacts(events=tuple(events), queue=queue)


def _pending_ids(events: list[dict[str, Any]]) -> set[str]:
    """Item ids referenced by ask/stage events without a terminal answer."""
    opened: set[str] = set()
    closed: set[str] = set()
    for event in events:
        kind = event.get("event")
        item = event.get("question_id") or event.get("item_id")
        if not isinstance(item, str) or not item:
            continue
        if kind in ("asked", "assumption_staged", "confirm_presented"):
            opened.add(item)
        elif kind in ("answered", "item_confirmed", "item_rejected",
                      "item_revised"):
            closed.add(item)
    return opened - closed


def _item_id(item: Any) -> Any:
    """Identity of a confirmation-batch item (``field`` for dict items)."""
    if isinstance(item, dict):
        return item.get("field")
    return item


def derive_queue(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Derive queue.json state from the append-only event log.

    Derived view (shaping-prototype 4.1): pending questions (asked, not
    answered), staged assumptions (staged, not confirmed/rejected/revised),
    and confirmation batches (presented, not fully decided).

    Batches close at item granularity: ``item_confirmed`` /
    ``item_rejected`` / ``item_revised`` events settle only the presented
    item whose id (dict ``field`` or the bare string) they carry, so a
    partially decided batch stays listed with its undecided items and a
    batch leaves ``open_confirmations`` only once every presented item has
    a terminal decision.
    """
    pending: list[dict[str, Any]] = []
    staged: list[dict[str, Any]] = []
    confirmations: list[dict[str, Any]] = []
    for event in events:
        kind = event.get("event")
        if kind == "asked":
            pending.append({
                "question_id": event.get("question_id"),
                "tier": event.get("tier"),
                "text": event.get("text"),
                "impact": event.get("impact"),
            })
        elif kind == "assumption_staged":
            staged.append({
                "field": event.get("field"),
                "tier": event.get("tier"),
                "reason": event.get("reason"),
                "risk": event.get("risk"),
                "fallback": event.get("fallback"),
            })
        elif kind == "confirm_presented":
            confirmations.append({
                "batch": event.get("batch"),
                "kind": event.get("kind"),
                "items": event.get("items", []),
            })
        elif kind == "answered":
            pending = [
                item for item in pending
                if item.get("question_id") != event.get("question_id")
            ]
        elif kind in ("item_confirmed", "item_rejected", "item_revised"):
            field_path = event.get("field")
            staged = [
                item for item in staged
                if item.get("field") != field_path
            ]
            if (
                isinstance(event.get("batch"), str)
                and isinstance(field_path, str) and field_path
            ):
                batch_name = event.get("batch")
                settled: list[dict[str, Any]] = []
                for batch in confirmations:
                    if batch.get("batch") != batch_name:
                        settled.append(batch)
                        continue
                    remaining = [
                        item for item in batch.get("items", [])
                        if _item_id(item) != field_path
                    ]
                    if remaining:
                        settled.append({**batch, "items": remaining})
                confirmations = settled
    return {
        "derived_from": "shaping-log.jsonl",
        "pending_questions": pending,
        "staged_assumptions": staged,
        "open_confirmations": confirmations,
    }


def queue_state(events: list[dict[str, Any]]) -> str:
    """Narrative session state: suspended / open / archived / replayed."""
    saw_suspended = False
    for event in events:
        if event.get("event") == "suspended":
            saw_suspended = True
        elif event.get("event") == "resumed":
            saw_suspended = False
        elif event.get("event") == "archived":
            return "archived"
        elif event.get("event") == "superseded_by":
            return "superseded"
    return "suspended" if saw_suspended else "open"
