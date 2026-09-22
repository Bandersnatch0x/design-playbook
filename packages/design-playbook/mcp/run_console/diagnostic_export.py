"""Diagnostic export contract v1 (ADR-0044, spec 2026-09-22-diagnostic-export-v1).

This module is the pure projection from a validated Snapshot v1 document to
the shareable export pair: one versioned JSON contract and one Markdown
human view. It owns the field table (spec §3), the canonical serialization,
the preview hash, and the Markdown rendering — and nothing else. It opens no
socket, spawns no process, and touches no file: the transaction seam
(``session``/``http_server``) stages and commits the pair; this module never
sees a path.

Export identity follows the contract spec: one transaction writes exactly
one JSON document and one Markdown view derived deterministically from the
same inputs. Every projected fact is an envelope
``{"availability", "reasonCode", "value"}`` carrying the snapshot's domain
result only when availability is ``known`` — the export never guesses,
never strengthens, and never substitutes a stale value for a current one.
"""
from __future__ import annotations

import hashlib
import json

EXPORT_CONTRACT_ID = "diagnostic-export.schema.v1"
EXPORT_CONTRACT_VERSION = 1

TRIAL_PROTOCOL_DOC = "docs/agents/run-console-read-only-trial.md"

# Fixed serialization (contract spec §4.1): the preview hash is SHA-256 over
# exactly these bytes, so the participant reviews the bytes that are named.
_CANONICAL_JSON_KWARGS = {
    "ensure_ascii": False,
    "sort_keys": True,
    "indent": 2,
}

_USAGE = {
    "evidence": False,
    "acceptanceInput": False,
    "upload": "none-manual-share-only",
}

# The transaction bindings the written pair states in-band (the gate's
# derivation reads them from the record itself — never synthesized).
# ``previewHash`` is deliberately absent: it is the hash of these bytes.
_TRANSACTION_FACTS = {
    "participantReviewed": True,
    "atomicJsonAndMarkdown": True,
    "confinedToTrialExport": True,
}

_NOT_COLLECTED = {
    "comprehensionTiming": (
        "human-observed and human-recorded by the trial facilitator; the "
        "product collects no timing"
    ),
    "participantAnswers": (
        "human-recorded by the trial facilitator; the product collects no "
        "answers"
    ),
    "interventionRecords": (
        "disclosed by the facilitator per the trial protocol; the product "
        "records none"
    ),
}


class ExportInputError(ValueError):
    """A typed rejection of a snapshot document that cannot be projected.

    The transaction seam validates the served snapshot before calling; this
    guard keeps a structurally impossible input from becoming a quiet
    falsified export (fail closed, same bargain as the snapshot builder).
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.code = "EXPORT_INPUT_INVALID"


def _require_mapping(value: object, what: str) -> dict:
    if not isinstance(value, dict):
        raise ExportInputError(f"{what} is missing or malformed")
    return value


def _require(value: object, what: str) -> dict:
    envelope = _require_mapping(value, what)
    for key in ("availability", "reason", "result"):
        if key not in envelope:
            raise ExportInputError(f"{what} is missing its assertion fields")
    return envelope


def _project(envelope: dict) -> dict:
    """Project one snapshot assertion to the export envelope shape."""
    reason = envelope.get("reason")
    return {
        "availability": envelope["availability"],
        "reasonCode": None
        if not isinstance(reason, dict)
        else reason.get("code"),
        "value": envelope["result"] if envelope["availability"] == "known" else None,
    }


def canonical_json_bytes(document: dict) -> bytes:
    """Serialize the export document to its canonical preview bytes.

    Fixed contract-spec serialization: UTF-8, ``ensure_ascii=False``,
    sorted keys, 2-space indent, one trailing newline. The preview hash is
    SHA-256 over exactly these bytes, so the participant reviews the bytes
    the hash names.
    """
    return (
        json.dumps(document, **_CANONICAL_JSON_KWARGS).encode("utf-8") + b"\n"
    )


def preview_hash(document: dict) -> str:
    """SHA-256 hex digest over the canonical JSON bytes."""
    return hashlib.sha256(canonical_json_bytes(document)).hexdigest()


def _fmt(envelope: dict) -> str:
    """Render one envelope for Markdown: value or availability+reason."""
    if envelope.get("availability") == "known":
        value = envelope.get("value")
        if value is None or value == "":
            return "—"
        if isinstance(value, dict):
            parts = []
            for key in ("runId", "label", "name", "version", "declaredTier",
                        "effectiveTier", "confirmedBy", "rounds", "closeReason",
                        "waitingForHuman", "owner", "role", "kind", "label"):
                if key in value and value[key] is not None:
                    parts.append(f"{key}: {value[key]}")
            return "; ".join(parts) if parts else json.dumps(
                value, ensure_ascii=False, sort_keys=True
            )
        return str(value)
    label = envelope.get("availability") or "unknown"
    code = envelope.get("reasonCode")
    return f"**{label}**" + (f" (`{code}`)" if code else "")


def _findings_lines(document: dict) -> list[str]:
    lines = []
    for finding in document["blockers"]["findings"]:
        if finding.get("availability") != "known":
            lines.append(
                f"- finding assertion **{finding['availability']}**"
                + (f" (`{finding['reasonCode']}`)" if finding.get("reasonCode") else "")
            )
            continue
        lines.append(
            f"- `{finding.get('findingId')}` [{finding.get('severity')} / "
            f"{finding.get('disposition')}] {finding.get('issue')} — owner: "
            f"{finding.get('ownerKind')}; repair: {finding.get('repair')}"
        )
    return lines


def render_markdown(document: dict) -> str:
    """Render the Markdown human view from the same document (spec §5)."""
    contract = document["exportContract"]
    lines: list[str] = []
    header = (
        f"# Diagnostic export — run `{document['run']['runId'] or 'unknown'}`",
        "",
        f"- Contract: `{contract['id']}` v{contract['version']}",
        f"- Snapshot built at: {document['run']['builtAt']} "
        f"({document['run']['buildState']})",
    )
    lines.extend(header)
    if document.get("participantRef"):
        lines.append(f"- Participant ref: {document['participantRef']}")
    lines.extend(
        (
            "- Usage boundary: **not Evidence**, **not an acceptance input**, "
            "no upload — manual share only, reviewed by the participant first",
            f"- Source-set hash: `{document['run']['sourceSetHash']}`",
            "",
            "## Comprehension facts",
            "",
            f"1. **Intent** — {_fmt(document['intent'])}",
            f"2. **Source verdict** — {_fmt(document['verdict'])}",
        )
    )
    lines.append("3. **Blockers** —")
    finding_lines = _findings_lines(document)
    if finding_lines:
        lines.extend(finding_lines)
    else:
        lines.append("   - none blocking")
    for item in document["blockers"]["limitations"]:
        lines.append(f"   - limitation `{item['code']}`: {item['summary']}")
    lines.append(f"4. **Next owner** — {_fmt(document['nextAction'])}")
    lines.extend(
        (
            "",
            "## Loop and progress",
            "",
            f"- Repair loop: {_fmt(document['loop'])}",
            f"- Progress: {_fmt(document['progress'])}",
            "",
            "## Counts",
            "",
            f"- Criteria known/total: "
            f"{document['counts']['criteriaKnown']}/{document['counts']['criteriaTotal']}",
        )
    )
    coverage = document["counts"]["coverage"]
    if coverage is not None:
        lines.append(
            f"- Coverage declared/reviewed/unreviewed: "
            f"{coverage['declared']}/{coverage['reviewed']}/{coverage['unreviewed']} "
            f"(complete: {coverage['complete']})"
        )
    lines.extend(
        (
            "",
            "## Not collected",
            "",
        )
    )
    for key, statement in document["notCollected"].items():
        lines.append(f"- {key}: {statement}")
    lines.extend(
        (
            "",
            f"Intervention disclosure companion: `{TRIAL_PROTOCOL_DOC}`.",
            "",
        )
    )
    return "\n".join(lines)


def build_export_document(
    snapshot: dict, *, participant_ref: str | None = None
) -> dict:
    """Project one validated Snapshot v1 document to the export JSON.

    Field table: spec §3. The projection is a PURE function of its two
    inputs — the validated snapshot and the participant-supplied reference
    — with no clock inside: the write phase re-derives the candidate and
    compares preview hashes, so any time-varying field inside the hashed
    bytes would break the preview-to-write binding on a live clock. When
    the pair was written is carried by the file name and the filesystem,
    not by a field inside the hash. ``participant_ref`` is echoed verbatim
    or omitted; it is never generated, defaulted, or persisted here.
    """
    if not isinstance(snapshot, dict) or snapshot.get("schemaVersion") != 1:
        raise ExportInputError("snapshot document is not a validated v1 document")
    identity = _require_mapping(snapshot.get("identity"), "identity")
    intent = _require_mapping(snapshot.get("intent"), "intent")
    execution = _require_mapping(snapshot.get("execution"), "execution")
    evaluation = _require_mapping(snapshot.get("evaluation"), "evaluation")
    next_actions = _require_mapping(snapshot.get("nextActions"), "nextActions")
    limitations = _require_mapping(snapshot.get("limitations"), "limitations")
    sources = _require_mapping(snapshot.get("sources"), "sources")

    snapshot_meta = _require_mapping(identity.get("snapshot"), "identity.snapshot")
    run_env = _require(identity.get("run"), "identity.run")
    product_env = _require(identity.get("product"), "identity.product")
    profile_env = _require(identity.get("profile"), "identity.profile")
    intent_env = _require(intent.get("summary"), "intent.summary")
    verdict_env = _require(evaluation.get("verdict"), "evaluation.verdict")
    progress_env = _require(execution.get("progress"), "execution.progress")
    repair_env = _require(execution.get("repair"), "execution.repair")
    next_env = _require(next_actions.get("primary"), "nextActions.primary")
    coverage_env = _require(evaluation.get("coverage"), "evaluation.coverage")

    # Blocking findings + limitations = comprehension fact 3. A finding is
    # blocking by its own disposition; a non-known finding assertion still
    # contributes its availability so the export shows what it could not read.
    findings = []
    for item in evaluation.get("findings", []):
        env = _require(item, "evaluation.findings[]")
        result = env.get("result")
        projected = {
            "availability": env["availability"],
            "reasonCode": None
            if not isinstance(env.get("reason"), dict)
            else env["reason"].get("code"),
        }
        if env["availability"] == "known" and isinstance(result, dict):
            projected.update(
                {
                    "findingId": result.get("findingId"),
                    "severity": result.get("severity"),
                    "disposition": result.get("disposition"),
                    "issue": result.get("issue"),
                    "ownerKind": (result.get("owner") or {}).get("kind"),
                    "repair": result.get("repair"),
                }
            )
        findings.append(projected)
    findings = [f for f in findings if f.get("disposition") == "blocking" or f.get("availability") != "known"]

    limitation_items = []
    for item in limitations.get("items", []):
        env = _require(item, "limitations.items[]")
        result = env.get("result")
        if env["availability"] == "known" and isinstance(result, dict):
            limitation_items.append(
                {"code": result.get("code"), "summary": result.get("summary")}
            )
        else:
            limitation_items.append(
                {
                    "code": None
                    if not isinstance(env.get("reason"), dict)
                    else env["reason"].get("code"),
                    "summary": f"limitation assertion is {env['availability']}",
                }
            )

    # The next action's copyable command text is never exported — only the
    # fact that one exists (spec §3 exclusions).
    next_result = next_env.get("result") if isinstance(next_env.get("result"), dict) else {}
    owner_result = next_result.get("owner") if isinstance(next_result.get("owner"), dict) else {}
    next_action = {
        "availability": next_env["availability"],
        "reasonCode": None
        if not isinstance(next_env.get("reason"), dict)
        else next_env["reason"].get("code"),
        "value": None
        if next_env["availability"] != "known"
        else {
            "owner": owner_result.get("actor"),
            "role": owner_result.get("role"),
            "kind": next_result.get("kind"),
            "label": next_result.get("label"),
            "hasCopyableCommand": bool(next_result.get("copyableAgentCommand")),
            "resumeStage": next_result.get("resumeStage"),
            "recaptureRequirement": next_result.get("recaptureRequirement"),
        },
    }

    evaluation_criteria = evaluation.get("criteria", [])
    criterion_count = sum(
        1
        for item in evaluation_criteria
        if isinstance(item, dict) and item.get("availability") == "known"
    )

    if participant_ref is not None and not isinstance(participant_ref, str):
        raise ExportInputError("participantRef must be a string or absent")
    if participant_ref == "":
        participant_ref = None

    # run: flat identity facts under their own envelope — runId/label carry
    # values only when the run assertion is known; availability/reasonCode
    # name what could not be read otherwise.
    run_result = run_env.get("result") if isinstance(run_env.get("result"), dict) else {}
    run = {
        "availability": run_env["availability"],
        "reasonCode": None
        if not isinstance(run_env.get("reason"), dict)
        else run_env["reason"].get("code"),
        "runId": run_result.get("runId"),
        "label": run_result.get("label"),
        "sourceSetHash": sources.get("sourceSetHash"),
        "builtAt": snapshot_meta.get("builtAt"),
        "buildState": snapshot_meta.get("buildState"),
        "snapshotSchemaVersion": snapshot.get("schemaVersion"),
    }

    document = {
        "exportContract": {
            "id": EXPORT_CONTRACT_ID,
            "version": EXPORT_CONTRACT_VERSION,
        },
        "participantRef": participant_ref,
        "usage": dict(_USAGE),
        "run": run,
        "product": _project(product_env),
        "profile": _project(profile_env),
        "intent": _project(intent_env),
        "verdict": _project(verdict_env),
        "blockers": {
            "findings": findings,
            "limitations": limitation_items,
        },
        "nextAction": next_action,
        "loop": _project(repair_env),
        "progress": _project(progress_env),
        "counts": {
            "criteriaKnown": criterion_count,
            "criteriaTotal": len(evaluation_criteria),
            "coverage": {
                "declared": coverage_env.get("result", {}).get("declared"),
                "reviewed": coverage_env.get("result", {}).get("reviewed"),
                "unreviewed": coverage_env.get("result", {}).get("unreviewed"),
                "complete": coverage_env.get("result", {}).get("complete"),
            }
            if isinstance(coverage_env.get("result"), dict)
            else None,
        },
        "transaction": dict(_TRANSACTION_FACTS),
        "notCollected": dict(_NOT_COLLECTED),
    }
    return document
