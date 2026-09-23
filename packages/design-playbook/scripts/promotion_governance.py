"""Component/token promotion governance — append-only, user-gated (T-068).

Reuses the ``rules-governance.jsonl`` discipline (append-only, stable unique
ids, ``supersedes`` pointing back, ISO-8601 timestamps) but for the component
backflow axis (spec 2026-09-22). The log records only *events*; recomputable
candidate counts live in ``component_candidates.py``, never here.

Schema decision (recorded per ticket): two promotion-scoped event types rather
than overloading the rule axis's ``candidate_opened``/``adjudicated`` — those
carry rule-specific reference shapes (``CANDIDATE_ID_PATTERN``,
``rule_id``/``target_version``/promotion criteria) that do not fit a component
path or token. The decisive boundary is identical to the rule axis (G7):

- ``promotion_candidate_opened`` — recording event an agent may append
  (``decided_by: agent``); a derivation or distill run opens a candidate.
- ``promotion_decided`` — **user-only** (``decided_by: user``); an agent may
  never write it. ``decision``: promote | reject | defer.

``kind``: component | token (the axis T-067 derives; token promotion lands in
T-072 but the event axis already carries it).

Event shapes::

    promotion_candidate_opened  {id, event, decided_by: agent, confirmed_at,
                                 kind, target, candidate_id?, rationale,
                                 evidence_refs[]}
    promotion_decided           {id, event, decided_by: user, confirmed_at,
                                 kind, target, decision, rationale,
                                 supersedes?}

``target`` is the promoted thing: a component path (component) or a token name
(token). ``candidate_id`` links back to the derivation's candidate when known.
"""
from __future__ import annotations

import re

try:
    from design_playbook.scripts.governance_jsonl import append_line, parse_events
except ImportError:  # standalone script import (sibling module)
    import importlib.util
    from pathlib import Path
    _gj_spec = importlib.util.spec_from_file_location(
        "governance_jsonl",
        Path(__file__).resolve().with_name("governance_jsonl.py"))
    _gj = importlib.util.module_from_spec(_gj_spec)
    _gj_spec.loader.exec_module(_gj)  # type: ignore[union-attr]
    append_line = _gj.append_line
    parse_events = _gj.parse_events

PROMOTION_EVENTS = frozenset({
    "promotion_candidate_opened", "promotion_decided",
})
PROMOTION_USER_DECISIVE = frozenset({"promotion_decided"})
PROMOTION_KINDS = frozenset({"component", "token"})
PROMOTION_DECISIONS = frozenset({"promote", "reject", "defer"})
PROMOTION_DECIDED_BY = frozenset({"user", "agent"})

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_TS_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$")


def _raw_append(path, event: dict) -> None:
    """Append without validation — test/seam use only.

    The write gate (``user_promotions``) and validators must reject an
    out-of-boundary event on *read*, not rely on it never being written; a
    hostile or buggy writer could bypass ``append_event``. Tests use this to
    confirm the read side stays fail-closed.
    """
    append_line(path, event)


def append_event(path, event: dict) -> None:
    """Append one validated event to the log (one JSON object per line).

    Validates first: a malformed or boundary-violating event is never written.
    The append is a single line — append-only discipline means existing lines
    are never rewritten, reordered, or deleted.
    """
    errors = validate_promotion_events([event])
    if errors:
        raise ValueError("invalid promotion event: " + "; ".join(errors))
    _raw_append(path, event)


def parse_promotion_log(text: str) -> list[dict]:
    """Parse one JSON event per line; blank lines skipped; malformed JSON
    raises ValueError naming the line number."""
    return parse_events(text, log_label="promotion log")


def validate_promotion_events(events: list[dict]) -> list[str]:
    """Schema + boundary validation. Returns failure descriptions
    (empty = valid)."""
    errors: list[str] = []
    ids: dict[str, int] = {}
    for index, event in enumerate(events, 1):
        label = str(event.get("id", f"line-{index}"))
        kind = str(event.get("event", ""))
        if kind not in PROMOTION_EVENTS:
            errors.append(
                f"{label}: event {kind!r} not in "
                f"{{{'|'.join(sorted(PROMOTION_EVENTS))}}}")
            continue

        event_id = event.get("id")
        if not isinstance(event_id, str) or not _ID_RE.match(event_id):
            errors.append(f"{label}: id {event_id!r} fails the stable-id pattern")
        elif event_id in ids:
            errors.append(
                f"{label}: duplicate event id (append-only: ids never repeat)")
        else:
            ids[event_id] = index

        for key in ("rationale", "target", "kind"):
            value = event.get(key)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{label}: {kind} requires a non-empty {key}")

        if isinstance(event.get("kind"), str) \
                and event["kind"] not in PROMOTION_KINDS:
            errors.append(
                f"{label}: kind {event['kind']!r} not in "
                f"{{{'|'.join(sorted(PROMOTION_KINDS))}}}")

        confirmed_at = event.get("confirmed_at")
        if not isinstance(confirmed_at, str) or not _TS_RE.match(confirmed_at):
            errors.append(
                f"{label}: confirmed_at must be an ISO-8601 timestamp")

        decided_by = event.get("decided_by")
        if decided_by not in PROMOTION_DECIDED_BY:
            errors.append(f"{label}: decided_by {decided_by!r} not in user|agent")
        if kind in PROMOTION_USER_DECISIVE and decided_by != "user":
            errors.append(
                f"{label}: {kind} is user-decisive — decided_by must be "
                "'user'; an agent may never write it")

        if kind == "promotion_candidate_opened":
            refs = event.get("evidence_refs")
            if not isinstance(refs, list) or not refs or not all(
                    isinstance(ref, str) and ref.strip() for ref in refs):
                errors.append(
                    f"{label}: promotion_candidate_opened requires "
                    "evidence_refs — a non-empty list of run/evidence refs")
        if kind == "promotion_decided":
            decision = event.get("decision")
            if decision not in PROMOTION_DECISIONS:
                errors.append(
                    f"{label}: decision {decision!r} not in "
                    f"{{{'|'.join(sorted(PROMOTION_DECISIONS))}}}")

    for index, event in enumerate(events, 1):
        label = str(event.get("id", f"line-{index}"))
        supersedes = event.get("supersedes")
        if supersedes is None:
            continue
        if not isinstance(supersedes, str) or not _ID_RE.match(supersedes):
            errors.append(f"{label}: supersedes {supersedes!r} fails the id pattern")
            continue
        target_index = ids.get(supersedes)
        if target_index is None:
            errors.append(f"{label}: supersedes unknown event id {supersedes!r}")
        elif target_index >= index:
            errors.append(
                f"{label}: supersedes must point at an earlier event")
    return errors


def user_promotions(events: list[dict]) -> dict[str, dict]:
    """Map (kind, target) -> latest user ``promote`` decision.

    T-070's write gate consumes this: a component may be merged into DESIGN.md
    only when a user-decisive ``promotion_decided``/``promote`` event names it.
    """
    accepted: dict[str, dict] = {}
    for event in events:
        if (event.get("event") == "promotion_decided"
                and event.get("decision") == "promote"
                and event.get("decided_by") == "user"):
            key = f"{event.get('kind')}::{event.get('target')}"
            accepted[key] = event
    return accepted
