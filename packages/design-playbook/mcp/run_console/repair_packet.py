"""Derived Repair Packet view over a validated Run Snapshot v1 document.

The packet is a read-only projection of owner-projected Snapshot facts. It
is not a schema, is not persisted, and is not a second finding, verdict,
or repair authority. Missing owner, command, recapture, or
invalidated-evidence facts stay explicit evidence gaps; prose is never
parsed to fill them. The projection writes nothing and executes nothing.
"""
from __future__ import annotations

from typing import Any, Mapping

from .contract import validate_snapshot

NOT_PRODUCED = "not-produced"

MSG_ABSENT_ASSERTION = "This assertion is absent from the snapshot."
MSG_NO_BLOCKING = "No blocking finding is projected in this snapshot."
MSG_DISPOSITION_UNKNOWN = (
    "A finding is present but its blocking disposition is not owner-known."
)
MSG_NO_INVALIDATED = (
    "The snapshot does not project an invalidated-evidence set."
)
MSG_NO_RECAPTURE = "The snapshot does not project a recapture requirement."
MSG_NO_COMMAND = (
    "This action carries no copyable agent command in the snapshot."
)

PACKET_KEYS = (
    "intent",
    "verdict",
    "finding",
    "blockerSource",
    "declarationOwner",
    "repairIntent",
    "nextOwner",
    "invalidatedEvidence",
    "resumeStage",
    "nextCommand",
    "recaptureRequirement",
)

_READABLE_AVAILABILITY = frozenset({"known", "stale", "inconsistent"})
_BLOCKING = "blocking"


def _reason(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _fact(
    *,
    availability: str,
    value: object = None,
    reason: dict[str, str] | None = None,
    source_id: str | None = None,
) -> dict[str, Any]:
    return {
        "availability": availability,
        "value": value,
        "reason": reason,
        "sourceId": source_id,
    }


def _gap(message: str, *, source_id: str | None = None) -> dict[str, Any]:
    return _fact(
        availability="unknown",
        value=None,
        reason=_reason(NOT_PRODUCED, message),
        source_id=source_id,
    )


def _from_assertion(assertion: object) -> dict[str, Any]:
    if not isinstance(assertion, dict):
        return _gap(MSG_ABSENT_ASSERTION)
    availability = assertion.get("availability")
    if availability not in {"known", "unknown", "stale", "inconsistent"}:
        availability = "unknown"
    source_id = assertion.get("id")
    source_id = source_id if isinstance(source_id, str) else None
    reason = assertion.get("reason")
    reason_obj = reason if isinstance(reason, dict) else None
    result = assertion.get("result")
    if availability in _READABLE_AVAILABILITY:
        return _fact(
            availability=availability,
            value=result,
            reason=reason_obj if availability != "known" else None,
            source_id=source_id,
        )
    return _fact(
        availability="unknown",
        value=None,
        reason=reason_obj,
        source_id=source_id,
    )


def _disposition(assertion: Mapping[str, Any]) -> str | None:
    result = assertion.get("result")
    if not isinstance(result, dict):
        return None
    disposition = result.get("disposition")
    if disposition in {"blocking", "advisory", "info"}:
        return disposition
    return None


def _select_blocking_finding(
    findings: object,
) -> tuple[str, dict[str, Any] | None, int]:
    """Return (kind, subject assertion, blocking count) in owner order.

    kind is ``present``, ``disposition-unknown``, or ``absent``. A missing
    disposition is never treated as non-blocking.
    """
    items = findings if isinstance(findings, list) else []
    subject: dict[str, Any] | None = None
    unreadable: dict[str, Any] | None = None
    blocking_count = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        disposition = _disposition(item)
        if disposition == _BLOCKING:
            blocking_count += 1
            if subject is None:
                subject = item
        elif disposition is None and unreadable is None:
            unreadable = item
    if subject is not None:
        return ("present", subject, blocking_count)
    if unreadable is not None:
        return ("disposition-unknown", unreadable, 0)
    return ("absent", None, 0)


def _owner_value(result: Mapping[str, Any]) -> dict[str, Any]:
    owner = result.get("owner")
    if not isinstance(owner, dict):
        return {"kind": None, "domainId": None, "sourceRef": None}
    kind = owner.get("kind")
    return {
        "kind": kind if isinstance(kind, str) else None,
        "domainId": owner.get("domainId"),
        "sourceRef": owner.get("sourceRef"),
    }


def _finding_fields(
    kind: str, assertion: dict[str, Any] | None
) -> dict[str, dict[str, Any]]:
    if kind == "absent":
        gap = _gap(MSG_NO_BLOCKING)
        return {
            "finding": gap,
            "blockerSource": gap,
            "declarationOwner": gap,
            "repairIntent": gap,
        }
    if kind == "disposition-unknown":
        base = _from_assertion(assertion)
        gap = _fact(
            availability=base["availability"],
            value=None,
            reason=base["reason"]
            or _reason(NOT_PRODUCED, MSG_DISPOSITION_UNKNOWN),
            source_id=base["sourceId"],
        )
        return {
            "finding": gap,
            "blockerSource": gap,
            "declarationOwner": gap,
            "repairIntent": gap,
        }
    assert assertion is not None
    projected = _from_assertion(assertion)
    result = projected["value"] if isinstance(projected["value"], dict) else None
    if result is None:
        empty = _fact(
            availability=projected["availability"],
            value=None,
            reason=projected["reason"],
            source_id=projected["sourceId"],
        )
        return {
            "finding": empty,
            "blockerSource": empty,
            "declarationOwner": empty,
            "repairIntent": empty,
        }
    owner = _owner_value(result)
    finding_value = {
        "findingId": result.get("findingId"),
        "criterionIds": list(result["criterionIds"])
        if isinstance(result.get("criterionIds"), list)
        else [],
        "issue": result.get("issue"),
        "severity": result.get("severity"),
        "disposition": result.get("disposition"),
    }
    blocker_value = {
        "issue": result.get("issue"),
        "findingId": result.get("findingId"),
        "sourceRef": owner["sourceRef"],
        "domainId": owner["domainId"],
    }
    repair = result.get("repair")
    return {
        "finding": _fact(
            availability=projected["availability"],
            value=finding_value,
            reason=projected["reason"],
            source_id=projected["sourceId"],
        ),
        "blockerSource": _fact(
            availability=projected["availability"],
            value=blocker_value,
            reason=projected["reason"],
            source_id=projected["sourceId"],
        ),
        "declarationOwner": _fact(
            availability=projected["availability"],
            value=owner,
            reason=projected["reason"],
            source_id=projected["sourceId"],
        ),
        "repairIntent": _fact(
            availability=projected["availability"],
            value=repair if isinstance(repair, str) else None,
            reason=projected["reason"],
            source_id=projected["sourceId"],
        ),
    }


def _resume_stage(progress: object) -> dict[str, Any]:
    projected = _from_assertion(progress)
    result = projected["value"] if isinstance(projected["value"], dict) else None
    if result is None:
        return projected
    stage_id = result.get("latestObservedStage")
    label = None
    stages = result.get("observedStages")
    if isinstance(stage_id, str) and isinstance(stages, list):
        for stage in stages:
            if isinstance(stage, dict) and stage.get("stageId") == stage_id:
                label = stage.get("label")
                break
    return _fact(
        availability=projected["availability"],
        value={"stageId": stage_id, "label": label if isinstance(label, str) else None},
        reason=projected["reason"],
        source_id=projected["sourceId"],
    )


def _next_owner(primary: object) -> dict[str, Any]:
    projected = _from_assertion(primary)
    result = projected["value"] if isinstance(projected["value"], dict) else None
    if result is None:
        return projected
    owner = result.get("owner")
    if not isinstance(owner, dict):
        return _fact(
            availability=projected["availability"],
            value={"actor": None, "role": None, "kind": result.get("kind"),
                   "actionId": result.get("actionId"), "label": result.get("label")},
            reason=projected["reason"],
            source_id=projected["sourceId"],
        )
    return _fact(
        availability=projected["availability"],
        value={
            "actor": owner.get("actor"),
            "role": owner.get("role"),
            "kind": result.get("kind"),
            "actionId": result.get("actionId"),
            "label": result.get("label"),
        },
        reason=projected["reason"],
        source_id=projected["sourceId"],
    )


def _next_command(primary: object) -> dict[str, Any]:
    projected = _from_assertion(primary)
    result = projected["value"] if isinstance(projected["value"], dict) else None
    if result is None:
        return projected
    command = result.get("copyableAgentCommand")
    if isinstance(command, str) and command:
        return _fact(
            availability=projected["availability"],
            value=command,
            reason=projected["reason"],
            source_id=projected["sourceId"],
        )
    if projected["availability"] == "known":
        return _gap(MSG_NO_COMMAND, source_id=projected["sourceId"])
    return _fact(
        availability=projected["availability"],
        value=None,
        reason=projected["reason"] or _reason(NOT_PRODUCED, MSG_NO_COMMAND),
        source_id=projected["sourceId"],
    )


def _copy_line(label: str, fact: Mapping[str, Any]) -> str:
    availability = str(fact.get("availability") or "unknown")
    reason = fact.get("reason")
    reason_text = ""
    if isinstance(reason, dict):
        code = reason.get("code")
        message = reason.get("message")
        if code or message:
            reason_text = f" ({code or ''}{': ' if code and message else ''}{message or ''})"
    value = fact.get("value")
    if availability not in _READABLE_AVAILABILITY or value in (None, "", [], {}):
        if availability == "known" and value in (None, "", [], {}):
            return f"{label} (known): (none)"
        return f"{label} ({availability}): unavailable{reason_text}"
    if isinstance(value, dict):
        parts = []
        for key, item in value.items():
            if item is None or item == []:
                parts.append(f"{key}=(none)")
            elif isinstance(item, list):
                parts.append(f"{key}={','.join(str(entry) for entry in item)}")
            else:
                parts.append(f"{key}={item}")
        rendered = "; ".join(parts) if parts else "(none)"
    else:
        rendered = str(value)
    stale = ""
    if availability in {"stale", "inconsistent"}:
        stale = " [stale context — not current]"
    return f"{label} ({availability}): {rendered}{stale}{reason_text}"


def format_packet_copy_text(packet: Mapping[str, Any]) -> str:
    """Plain-text copy of the derived packet. Never a command to execute."""
    lines = ["Repair Packet (derived view; copy only; nothing is executed)"]
    labels = {
        "intent": "Intent",
        "verdict": "Verdict",
        "finding": "Finding",
        "blockerSource": "Blocker source",
        "declarationOwner": "Declaration owner",
        "repairIntent": "Repair intent",
        "nextOwner": "Next owner",
        "invalidatedEvidence": "Invalidated evidence",
        "resumeStage": "Resume stage",
        "nextCommand": "Next Agent command",
        "recaptureRequirement": "Recapture requirement",
    }
    for key in PACKET_KEYS:
        fact = packet.get(key)
        if isinstance(fact, dict):
            lines.append(_copy_line(labels[key], fact))
    return "\n".join(lines)


def derive_repair_packet(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Return a JSON-serializable derived packet from a validated snapshot.

    The input is validated through the existing consumer contract and is
    never mutated. The result has no independent lifecycle.
    """
    document = validate_snapshot(snapshot)
    evaluation = document["evaluation"]
    kind, subject, blocking_count = _select_blocking_finding(evaluation.get("findings"))
    finding_fields = _finding_fields(kind, subject)
    if kind == "present" and isinstance(finding_fields["blockerSource"]["value"], dict):
        finding_fields["blockerSource"]["value"] = {
            **finding_fields["blockerSource"]["value"],
            "blockingCount": blocking_count,
        }
    primary = document["nextActions"]["primary"]
    packet = {
        "intent": _from_assertion(document["intent"]["summary"]),
        "verdict": _from_assertion(evaluation["verdict"]),
        **finding_fields,
        "nextOwner": _next_owner(primary),
        "invalidatedEvidence": _gap(MSG_NO_INVALIDATED),
        "resumeStage": _resume_stage(document["execution"]["progress"]),
        "nextCommand": _next_command(primary),
        "recaptureRequirement": _gap(MSG_NO_RECAPTURE),
    }
    packet["copyText"] = format_packet_copy_text(packet)
    return packet
