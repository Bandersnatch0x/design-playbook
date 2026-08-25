"""Executable consumer contract for disposable Run Snapshot v1 documents.

The public interface is deliberately small: callers submit one already parsed
JSON value to :func:`validate_snapshot` and receive either a detached complete
snapshot or one stable :class:`SnapshotContractError`.  Schema loading,
closed-shape checks, cross-document invariants, and safe error rendering stay
inside this module; callers never select a validator or duplicate these rules.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterator

SNAPSHOT_VERSION = 1
SNAPSHOT_VERSION_UNSUPPORTED = "SNAPSHOT_VERSION_UNSUPPORTED"
SNAPSHOT_CONTRACT_INVALID = "SNAPSHOT_CONTRACT_INVALID"

_SCHEMA_PATH = Path(__file__).with_name("snapshot_v1.schema.json")
_ERROR_MESSAGES = {
    SNAPSHOT_VERSION_UNSUPPORTED: "The Run Snapshot version is not supported.",
    SNAPSHOT_CONTRACT_INVALID: "The Run Snapshot does not satisfy the v1 contract.",
}
_ASSERTION_KEYS = frozenset(
    {"id", "availability", "result", "reason", "source", "approval"}
)
_UNKNOWN_REASON_CODES = frozenset(
    {
        "not-produced",
        "source-missing",
        "source-unreadable",
        "source-malformed",
        "source-version-unsupported",
        "no-canonical-value",
        "dependency-unavailable",
        "attestation-missing",
        "owner-unmapped",
        "partial-write",
    }
)
_STALE_REASON_CODES = frozenset(
    {"source-changed-during-build", "attestation-invalidated"}
)
_INCONSISTENT_REASON_CODES = frozenset(
    {"partial-write", "conflicting-authorities", "invariant-violation"}
)
_UNSAFE_TEXT_PATTERNS = (
    re.compile(r"(?i)traceback\s*\("),
    re.compile(r"(?i)authorization\s*:\s*bearer"),
    re.compile(r"(?i)\b(?:token|password|credential|secret)[-_ ]*[=:]\s*\S+"),
    re.compile(r"(?i)(?:[a-z]:[\\/]|(?:^|\s)/(?:home|users|tmp|var|etc)/)"),
)
_DYNAMIC_ASSERTION_PATHS = (
    ("intent", "criteria"),
    ("evaluation", "criteria"),
    ("evaluation", "findings"),
    ("nextActions", "alternatives"),
    ("limitations", "items"),
)


class SnapshotContractError(ValueError):
    """A safe, stable whole-document rejection at the consumer seam."""

    def __init__(self, code: str) -> None:
        super().__init__(_ERROR_MESSAGES[code])
        self.code = code

    def to_envelope(self, *, request_id: str) -> dict[str, Any]:
        """Return the fixed safe v1 error envelope for a server request."""
        if re.fullmatch(r"req_[A-Za-z0-9_-]{4,64}", request_id) is None:
            raise ValueError("request_id must be an ephemeral opaque request ID")
        return {
            "schemaVersion": SNAPSHOT_VERSION,
            "error": {
                "code": self.code,
                "message": str(self),
                "requestId": request_id,
                "retryable": False,
            },
        }


class _SchemaViolation(Exception):
    """Internal control flow; details never cross the public seam."""


def _load_schema() -> dict[str, Any]:
    with _SCHEMA_PATH.open(encoding="utf-8") as handle:
        schema = json.load(handle)
    if not isinstance(schema, dict):
        raise RuntimeError("Run Snapshot v1 schema root must be an object")
    return schema


_SCHEMA = _load_schema()


def _same_json_value(left: object, right: object) -> bool:
    return type(left) is type(right) and left == right


def _matches_type(value: object, expected: str) -> bool:
    return {
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
        "string": isinstance(value, str),
        "integer": type(value) is int,
        "number": type(value) in (int, float),
        "boolean": isinstance(value, bool),
        "null": value is None,
    }[expected]


def _resolve_ref(reference: str) -> dict[str, Any]:
    if not reference.startswith("#/"):
        raise RuntimeError("Run Snapshot schema may use local references only")
    node: object = _SCHEMA
    for segment in reference[2:].split("/"):
        if not isinstance(node, dict) or segment not in node:
            raise RuntimeError(f"Unresolvable Run Snapshot schema reference: {reference}")
        node = node[segment]
    if not isinstance(node, dict):
        raise RuntimeError(f"Run Snapshot schema reference is not an object: {reference}")
    return node


def _validate_schema(value: object, schema: dict[str, Any]) -> None:
    """Evaluate the closed JSON-Schema subset used by the bundled artifact."""
    reference = schema.get("$ref")
    if isinstance(reference, str):
        _validate_schema(value, _resolve_ref(reference))

    for branch in schema.get("allOf", ()):
        _validate_schema(value, branch)

    alternatives = schema.get("anyOf")
    if alternatives is not None:
        for branch in alternatives:
            try:
                _validate_schema(value, branch)
            except _SchemaViolation:
                continue
            break
        else:
            raise _SchemaViolation

    expected_type = schema.get("type")
    if expected_type is not None and not _matches_type(value, expected_type):
        raise _SchemaViolation
    if "const" in schema and not _same_json_value(value, schema["const"]):
        raise _SchemaViolation
    if "enum" in schema and not any(
        _same_json_value(value, candidate) for candidate in schema["enum"]
    ):
        raise _SchemaViolation

    if isinstance(value, dict):
        required = schema.get("required", ())
        if any(key not in value for key in required):
            raise _SchemaViolation
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False and not set(value) <= set(
            properties
        ):
            raise _SchemaViolation
        for key, child_schema in properties.items():
            if key in value:
                _validate_schema(value[key], child_schema)

    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            raise _SchemaViolation
        item_schema = schema.get("items")
        if item_schema is not None:
            for item in value:
                _validate_schema(item, item_schema)

    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            raise _SchemaViolation
        pattern = schema.get("pattern")
        if pattern is not None and re.search(pattern, value) is None:
            raise _SchemaViolation

    if type(value) in (int, float):
        minimum = schema.get("minimum")
        if minimum is not None and value < minimum:
            raise _SchemaViolation


def _at(document: dict[str, Any], path: tuple[str, ...]) -> Any:
    node: Any = document
    for segment in path:
        node = node[segment]
    return node


def _iter_assertions(document: dict[str, Any]) -> Iterator[dict[str, Any]]:
    fixed_paths = (
        ("identity", "run"),
        ("identity", "product"),
        ("identity", "profile"),
        ("intent", "summary"),
        ("intent", "contract"),
        ("execution", "progress"),
        ("execution", "preview"),
        ("execution", "repair"),
        ("evaluation", "verdict"),
        ("evaluation", "coverage"),
        ("nextActions", "primary"),
    )
    for path in fixed_paths:
        yield _at(document, path)
    for path in _DYNAMIC_ASSERTION_PATHS:
        yield from _at(document, path)


def _require_sorted_unique(values: list[str]) -> None:
    if values != sorted(values) or len(values) != len(set(values)):
        raise _SchemaViolation


def _validate_source_records(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    items = document["sources"]["items"]
    refs = [item["sourceRef"] for item in items]
    _require_sorted_unique(refs)
    records = dict(zip(refs, items))

    for item in items:
        observed = item["observedHash"]
        verified = item["verifiedHash"]
        verified_at = item["verifiedAt"]
        freshness = item["freshness"]
        if item["readState"] == "complete" and observed is None:
            raise _SchemaViolation
        if (verified is None) != (verified_at is None):
            raise _SchemaViolation
        if verified_at is not None and _parse_timestamp(verified_at) < _parse_timestamp(
            item["observedAt"]
        ):
            raise _SchemaViolation
        if freshness == "current" and (
            observed is None or verified is None or observed != verified
        ):
            raise _SchemaViolation
        if freshness == "changed" and (
            observed is None or verified is None or observed == verified
        ):
            raise _SchemaViolation
        if freshness == "unverified" and verified is not None:
            raise _SchemaViolation
    return records


def _parse_timestamp(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError:
        raise _SchemaViolation from None


def _validate_approval(
    assertion: dict[str, Any], source_records: dict[str, dict[str, Any]]
) -> None:
    approval = assertion["approval"]
    if approval is None:
        return
    if approval["sourceRef"] not in source_records:
        raise _SchemaViolation
    source_record = source_records[approval["sourceRef"]]
    current_source_hash = source_record["verifiedHash"]
    if current_source_hash is None:
        current_source_hash = source_record["observedHash"]
    if approval["sourceHash"] != current_source_hash:
        raise _SchemaViolation
    state = approval["state"]
    attestation_id = approval["attestationId"]
    availability = assertion["availability"]
    reason = assertion["reason"]
    reason_code = None if reason is None else reason["code"]
    if state == "missing" and (
        attestation_id is not None
        or availability != "unknown"
        or reason_code != "attestation-missing"
    ):
        raise _SchemaViolation
    if state == "valid" and (attestation_id is None or availability != "known"):
        raise _SchemaViolation
    if state == "invalidated" and (
        attestation_id is None
        or availability != "stale"
        or reason_code != "attestation-invalidated"
    ):
        raise _SchemaViolation


def _validate_assertion(
    assertion: dict[str, Any], source_records: dict[str, dict[str, Any]]
) -> None:
    if set(assertion) != _ASSERTION_KEYS:
        raise _SchemaViolation
    availability = assertion["availability"]
    result = assertion["result"]
    reason = assertion["reason"]
    source = assertion["source"]
    refs = source["refs"]
    _require_sorted_unique(refs)
    if any(ref not in source_records for ref in refs):
        raise _SchemaViolation

    observed = source["observedSetHash"]
    verified = source["verifiedSetHash"]
    if availability == "known":
        if result is None or reason is not None:
            raise _SchemaViolation
        if observed is None or verified is None or observed != verified:
            raise _SchemaViolation
    else:
        if reason is None:
            raise _SchemaViolation
        reason_refs = reason["sourceRefs"]
        _require_sorted_unique(reason_refs)
        if any(ref not in refs for ref in reason_refs):
            raise _SchemaViolation
        if any(pattern.search(reason["message"]) for pattern in _UNSAFE_TEXT_PATTERNS):
            raise _SchemaViolation
        if any(
            any(pattern.search(conflict["summary"]) for pattern in _UNSAFE_TEXT_PATTERNS)
            for conflict in reason["conflicts"]
        ):
            raise _SchemaViolation
        conflict_refs = [conflict["sourceRef"] for conflict in reason["conflicts"]]
        if any(ref not in reason_refs for ref in conflict_refs):
            raise _SchemaViolation
        code = reason["code"]
        if availability == "unknown" and (
            result is not None or code not in _UNKNOWN_REASON_CODES
        ):
            raise _SchemaViolation
        if availability == "stale":
            if code not in _STALE_REASON_CODES:
                raise _SchemaViolation
            if code == "source-changed-during-build" and (
                observed is None or verified is None or observed == verified
            ):
                raise _SchemaViolation
        if availability == "inconsistent" and (
            result is not None
            or code not in _INCONSISTENT_REASON_CODES
            or not reason["conflicts"]
        ):
            raise _SchemaViolation
    _validate_approval(assertion, source_records)


def _source_set_hash(items: list[dict[str, Any]]) -> str:
    retained = [
        {
            key: item[key]
            for key in (
                "sourceRef",
                "authorityKey",
                "readState",
                "observedHash",
                "verifiedHash",
                "freshness",
            )
        }
        for item in items
    ]
    encoded = json.dumps(
        retained,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _validate_invariants(document: dict[str, Any]) -> None:
    _parse_timestamp(document["identity"]["snapshot"]["builtAt"])
    source_records = _validate_source_records(document)
    assertions = list(_iter_assertions(document))
    assertion_ids = [assertion["id"] for assertion in assertions]
    if len(assertion_ids) != len(set(assertion_ids)):
        raise _SchemaViolation
    for path in _DYNAMIC_ASSERTION_PATHS:
        _require_sorted_unique([item["id"] for item in _at(document, path)])
    for assertion in assertions:
        _validate_assertion(assertion, source_records)

    source_set_hash = _source_set_hash(document["sources"]["items"])
    if document["sources"]["sourceSetHash"] != source_set_hash:
        raise _SchemaViolation
    snapshot_metadata = document["identity"]["snapshot"]
    if snapshot_metadata["sourceSetHash"] != source_set_hash:
        raise _SchemaViolation

    must_degrade = any(
        assertion["availability"] != "known" for assertion in assertions
    ) or any(item["freshness"] != "current" for item in source_records.values())
    expected_build_state = "degraded" if must_degrade else "current"
    if snapshot_metadata["buildState"] != expected_build_state:
        raise _SchemaViolation


def validate_snapshot(document: object) -> dict[str, Any]:
    """Validate one complete v1 document or reject it without partial output.

    Missing, non-integer (including ``bool``), and unknown versions are version
    errors.  Once integer version 1 is selected, every shape or semantic failure
    is one contract error.  Neither path includes rejected input details.
    """
    if not isinstance(document, dict):
        raise SnapshotContractError(SNAPSHOT_VERSION_UNSUPPORTED)
    if type(document.get("schemaVersion")) is not int:
        raise SnapshotContractError(SNAPSHOT_VERSION_UNSUPPORTED)
    if document["schemaVersion"] != SNAPSHOT_VERSION:
        raise SnapshotContractError(SNAPSHOT_VERSION_UNSUPPORTED)
    try:
        _validate_schema(document, _SCHEMA)
        _validate_invariants(document)
    except _SchemaViolation:
        raise SnapshotContractError(SNAPSHOT_CONTRACT_INVALID) from None
    return deepcopy(document)
