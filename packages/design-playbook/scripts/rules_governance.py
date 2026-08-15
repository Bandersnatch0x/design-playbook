"""rules-governance.jsonl — project-level append-only governance log
(vNext S5, rules-prototype 5.3 / Q7=A).

First-version schema, landed in S5 (the S1 spec placed the schema
definition in slice 1; the hook shipped empty then and this module is the
promised landing — see vnext-prototype 2.1 row 4). One JSON object per
line, living next to the persistent contract (``<project>/rules-
governance.jsonl``); runs never write it.

Append-only discipline (same philosophy as decisions.jsonl, ADR-0017):

- lines are only ever appended; existing events are never rewritten,
  reordered, or deleted;
- ``id`` is stable and unique — a superseding decision is a NEW event with
  ``supersedes`` pointing at the earlier event id;
- the log records only user-decisive events (open / defer / adjudicate /
  revise / exempt) — recomputable counts (distinct runs, context kinds)
  live in the derived candidate view (``learning_candidates.py``), never
  here;
- decisive events carry ``decided_by: user`` — an agent may never write
  them (G7 boundary: identity is not proven, user confirmation and agent
  recording are structurally distinguished);
- rule references pin ``ID@version`` via ``rule_id`` + ``target_version``
  (or ``rule_version`` for exemptions) — the same pinning discipline as
  audit rows and ``rule:`` finding lines.

Event schema (v1)::

    candidate_opened   {id, event, candidate_id, decided_by, confirmed_at,
                        rationale, evidence_refs[]}
    evidence_appended  {id, event, candidate_id, decided_by, confirmed_at,
                        rationale, evidence_refs[]}
    adjudicated        {id, event, candidate_id, rule_id, decision,
                        decided_by: user, confirmed_at, rationale,
                        target_status, target_version?, criteria?,
                        supersedes?}
    rule_revision      {id, event, rule_id, decided_by: user, confirmed_at,
                        rationale, supersedes?}
    exemption_granted  {id, event, rule_id, rule_version, decided_by: user,
                        confirmed_at, rationale, risk, supersedes?}
    exemption_reviewed {id, event, rule_id, decided_by: user, confirmed_at,
                        rationale, supersedes?}

``decision``: promote | reject | merge | defer. ``target_status``:
advisory | machine-enforced. Promoting to machine-enforced requires the
six promotion-criteria records (rules-prototype 5.2); promoting to
advisory requires the weaker panel (authority / risk / fp_cost).
"""
from __future__ import annotations

import json
import re

LOG_NAME = "rules-governance.jsonl"

EVENTS = frozenset({
    "candidate_opened", "evidence_appended", "adjudicated",
    "rule_revision", "exemption_granted", "exemption_reviewed",
})
# Decisive events record the user's decision; an agent may never write
# them (decided_by must be "user"). candidate_opened / evidence_appended
# are recording events the derivation or a review agent may append.
USER_DECISIVE_EVENTS = frozenset({
    "adjudicated", "rule_revision", "exemption_granted", "exemption_reviewed",
})
DECIDED_BY = frozenset({"user", "agent"})
DECISIONS = frozenset({"promote", "reject", "merge", "defer"})
TARGET_STATUSES = frozenset({"advisory", "machine-enforced"})
# rules-prototype 5.2: the six promotion criteria (machine-enforced needs
# all six; the advisory panel is the weaker subset marked below).
CRITERIA_KEYS = (
    "authority", "risk", "reproducible", "fp_cost", "fix_path", "validation",
)
ADVISORY_PANEL_KEYS = frozenset({"authority", "risk", "fp_cost"})

ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
RULE_ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*-[0-9]{2}$")
CANDIDATE_ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*-[0-9]{4}-[0-9]{2}-[0-9]{2}$")
TS_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$")

CANDIDATE_SCOPED_EVENTS = frozenset({"candidate_opened", "evidence_appended"})
RULE_SCOPED_EVENTS = frozenset({
    "rule_revision", "exemption_granted", "exemption_reviewed",
})


def parse_governance_log(text: str) -> list[dict]:
    """Parse one JSON event per line. Blank lines are skipped; malformed
    JSON raises ValueError naming the line number."""
    events: list[dict] = []
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValueError(f"governance log line {number}: bad JSON: {exc}") from exc
        if not isinstance(event, dict):
            raise ValueError(
                f"governance log line {number}: event must be a JSON object")
        events.append(event)
    return events


def _require(errors: list[str], event: dict, key: str) -> object:
    value = event.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        errors.append(f"{event.get('id', '<no id>')}: {event.get('event', '?')} "
                      f"requires a non-empty {key}")
    return value


def validate_governance_events(events: list[dict]) -> list[str]:
    """Schema validation (enums / required fields / reference existence).

    Returns a list of failure descriptions (empty = valid log).
    """
    errors: list[str] = []
    ids: dict[str, int] = {}

    for index, event in enumerate(events, 1):
        label = str(event.get("id", f"line-{index}"))
        kind = str(event.get("event", ""))

        if kind not in EVENTS:
            errors.append(
                f"{label}: event {kind!r} not in "
                f"{{{'|'.join(sorted(EVENTS))}}}")
            continue

        event_id = _require(errors, event, "id")
        if isinstance(event_id, str):
            if not ID_PATTERN.match(event_id):
                errors.append(f"{label}: id {event_id!r} fails the stable-id pattern")
            if event_id in ids:
                errors.append(
                    f"{label}: duplicate event id (append-only: ids never repeat)")
            ids[event_id] = index

        _require(errors, event, "rationale")
        confirmed_at = _require(errors, event, "confirmed_at")
        if isinstance(confirmed_at, str) and not TS_PATTERN.match(confirmed_at):
            errors.append(
                f"{label}: confirmed_at {confirmed_at!r} must be an ISO-8601 "
                "timestamp (e.g. 2026-08-14T00:00:00Z)")

        decided_by = _require(errors, event, "decided_by")
        if isinstance(decided_by, str) and decided_by not in DECIDED_BY:
            errors.append(
                f"{label}: decided_by {decided_by!r} not in user|agent")
        if kind in USER_DECISIVE_EVENTS and decided_by != "user":
            errors.append(
                f"{label}: {kind} is a user-decisive event — decided_by must "
                "be 'user'; an agent may never write it")

        if kind in CANDIDATE_SCOPED_EVENTS or kind == "adjudicated":
            candidate_id = _require(errors, event, "candidate_id")
            if (isinstance(candidate_id, str)
                    and not CANDIDATE_ID_PATTERN.match(candidate_id)):
                errors.append(
                    f"{label}: candidate_id {candidate_id!r} fails "
                    "CAND-<year>-<week>-<seq>")
        if kind in RULE_SCOPED_EVENTS or kind == "adjudicated":
            rule_id = _require(errors, event, "rule_id")
            if (isinstance(rule_id, str)
                    and not RULE_ID_PATTERN.match(rule_id)):
                errors.append(
                    f"{label}: rule_id {rule_id!r} fails <FAMILY>-<NN> "
                    "(e.g. ST-01)")

        if kind in CANDIDATE_SCOPED_EVENTS:
            refs = event.get("evidence_refs")
            if not isinstance(refs, list) or not refs or not all(
                    isinstance(ref, str) and ref.strip() for ref in refs):
                errors.append(
                    f"{label}: {kind} requires evidence_refs — a non-empty "
                    "list of run / evidence references")

        if kind == "adjudicated":
            decision = _require(errors, event, "decision")
            if isinstance(decision, str) and decision not in DECISIONS:
                errors.append(
                    f"{label}: decision {decision!r} not in "
                    f"{{{'|'.join(sorted(DECISIONS))}}}")
            target_status = _require(errors, event, "target_status")
            if (isinstance(target_status, str)
                    and target_status not in TARGET_STATUSES):
                errors.append(
                    f"{label}: target_status {target_status!r} not in "
                    "advisory|machine-enforced")
            target_version = event.get("target_version")
            if target_version is not None and (
                    not isinstance(target_version, int)
                    or isinstance(target_version, bool)
                    or target_version < 1):
                errors.append(
                    f"{label}: target_version must be a positive integer")
            criteria = event.get("criteria")
            if decision == "promote" and isinstance(target_status, str):
                if not isinstance(criteria, dict):
                    errors.append(
                        f"{label}: promote decisions require a criteria record")
                else:
                    if target_status == "machine-enforced":
                        missing = [
                            key for key in CRITERIA_KEYS
                            if not str(criteria.get(key, "")).strip()
                        ]
                        if missing:
                            errors.append(
                                f"{label}: machine-enforced promotion requires "
                                f"all six criteria records, missing {missing}")
                    elif target_status == "advisory":
                        missing = [
                            key for key in sorted(ADVISORY_PANEL_KEYS)
                            if not str(criteria.get(key, "")).strip()
                        ]
                        if missing:
                            errors.append(
                                f"{label}: advisory promotion requires the "
                                f"authority/risk/fp_cost panel, missing {missing}")

        if kind == "exemption_granted":
            rule_version = event.get("rule_version")
            if (not isinstance(rule_version, int) or isinstance(rule_version, bool)
                    or rule_version < 1):
                errors.append(
                    f"{label}: exemption_granted requires rule_version "
                    "(a positive integer, ID@version pinning)")
            _require(errors, event, "risk")

    # Reference existence: supersedes must point at an EARLIER event id.
    for index, event in enumerate(events, 1):
        label = str(event.get("id", f"line-{index}"))
        supersedes = event.get("supersedes")
        if supersedes is None:
            continue
        if not isinstance(supersedes, str) or not ID_PATTERN.match(supersedes):
            errors.append(f"{label}: supersedes {supersedes!r} fails the id pattern")
            continue
        target_index = ids.get(supersedes)
        if target_index is None:
            errors.append(f"{label}: supersedes unknown event id {supersedes!r}")
        elif target_index >= index:
            errors.append(
                f"{label}: supersedes must point at an earlier event "
                f"({supersedes!r} is at line {target_index}, not before {index})")
    return errors


def promote_adjudications(events: list[dict]) -> dict[str, dict]:
    """Map rule_id -> its machine-enforced promotion event (latest wins).

    The G8 governance-ref check consumes this: a machine-enforced registry
    entry must reference an adjudicated promote event whose target_status
    is machine-enforced for that rule.
    """
    promotions: dict[str, dict] = {}
    for event in events:
        if (event.get("event") == "adjudicated"
                and event.get("decision") == "promote"
                and event.get("target_status") == "machine-enforced"):
            rule_id = event.get("rule_id")
            if isinstance(rule_id, str):
                promotions[rule_id] = event
    return promotions


def validate_governance_file(path) -> list[str]:
    """Read + parse + validate a governance log file."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return [f"cannot read governance log {path}: {exc}"]
    try:
        events = parse_governance_log(text)
    except ValueError as exc:
        return [str(exc)]
    return validate_governance_events(events)

