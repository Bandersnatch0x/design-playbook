"""Closed typed-action allowlist for the run console (RCV1-009, ADR-0044).

This module is the single source of truth for which typed capabilities
the run console exposes. The allowlist is closed names: adding a
capability means editing this tuple and its tests together. Dispatch
stays in the HTTP layer — there is one server action route
(``POST /api/v1/actions/refresh``), the hash-bound source view is the
existing read route, and copy is browser-only clipboard work with no
server execution route. Diagnostic export (ADR-0044) is the one
run-tree-writing capability: its two routes live in the HTTP layer and
its effect in ``export_transaction.py``; this module owns only the
closed payload validators for its preview and write requests. Role
attestation stays explicitly disabled, and every forbidden action name
(repair, rerun, provider, file edit, upload, ...) has no entry here and
no route anywhere.

Nothing in this module opens a socket, spawns a process, or writes to
the run tree: the refresh effect is one full snapshot rebuild through
the RCV1-005 seams, and the export effect lives in its own module.
"""
from __future__ import annotations

import json

from .request_security import ACTION_PAYLOAD_INVALID
from .session import (
    SESSION_CLOSED,
    RunConsoleSession,
    RunConsoleSessionError,
)

# Codes owned here (request_security.py is frozen outside this change):
# a non-JSON content type on the one action route is a 415, not a 400.
CONTENT_TYPE_UNSUPPORTED = "CONTENT_TYPE_UNSUPPORTED"
CONTENT_TYPE_UNSUPPORTED_MESSAGE = (
    "The typed action requires an application/json request body."
)
# Spec section 13 keeps a body that does not decode as JSON at all
# distinct from valid JSON with the wrong fields: MALFORMED_JSON is the
# pre-dispatch decode rejection, ACTION_PAYLOAD_INVALID stays field-level.
MALFORMED_JSON = "MALFORMED_JSON"
MALFORMED_JSON_MESSAGE = "The request body is not well-formed JSON."

JSON_CONTENT_TYPE = "application/json"
ACTION_REFRESH = "refresh"
REFRESH_ROUTE = "/api/v1/actions/refresh"
REFRESH_ALLOWED_METHODS = "POST"
REFRESH_SCHEMA_VERSION = 1

# Diagnostic export (ADR-0044): one capability, two typed requests.
ACTION_EXPORT_PREVIEW = "diagnostic-export-preview"
ACTION_EXPORT_WRITE = "diagnostic-export-write"
EXPORT_SCHEMA_VERSION = 1

# Closed names only. Route and method live with the HTTP layer that
# actually dispatches them (ADR-0038 §5 allowlist as contract object,
# not as a second router).
CAPABILITIES: tuple[str, ...] = (
    ACTION_REFRESH,
    "view-source",
    "copy-agent-command",
    "diagnostic-export",
)


def capability_names() -> tuple[str, ...]:
    """The closed allowlist, in registry order."""
    return CAPABILITIES


class ActionPayloadError(ValueError):
    """A typed rejection of a body that is not the closed action payload."""

    def __init__(
        self, message: str = "The action payload is not the closed schema."
    ) -> None:
        super().__init__(message)
        self.code = ACTION_PAYLOAD_INVALID


class MalformedJSONError(ValueError):
    """A typed rejection of a body that does not decode as JSON at all.

    A deliberate sibling of :class:`ActionPayloadError`, never a subclass:
    spec section 13 keeps ``MALFORMED_JSON`` (rejected before action
    dispatch) distinct from the field-level ``ACTION_PAYLOAD_INVALID``,
    and a subclass would let one ``except ActionPayloadError`` fold the
    two codes back together.
    """

    def __init__(self, message: str = MALFORMED_JSON_MESSAGE) -> None:
        super().__init__(message)
        self.code = MALFORMED_JSON


def content_type_is_json(value: object) -> bool:
    """True only for an ``application/json`` Content-Type value.

    Parameters after the media type (a charset) are tolerated; anything
    else — another media type, a missing header, or a header repeated
    by the client — is not the one content type the action accepts.
    """
    if not isinstance(value, str):
        return False
    media_type = value.split(";", 1)[0].strip().lower()
    return media_type == JSON_CONTENT_TYPE


def parse_json_action_body(raw: object) -> object:
    """Decode one UTF-8 JSON request body or raise the typed rejection.

    Every decode failure — a body that is not a byte sequence, not
    UTF-8, or not one well-formed JSON document — is the pre-dispatch
    ``MALFORMED_JSON`` rejection. Valid JSON that is not the closed
    payload is judged later by :func:`validate_refresh_payload` and
    keeps ``ACTION_PAYLOAD_INVALID``.
    """
    if not isinstance(raw, (bytes, bytearray)):
        raise MalformedJSONError() from None
    try:
        return json.loads(bytes(raw).decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise MalformedJSONError() from None


def validate_refresh_payload(payload: object) -> None:
    """Accept exactly ``{"schemaVersion": 1, "action": "refresh"}``.

    No missing field, no unknown field, no other value, and no type
    confusion (a bool is not the integer 1) ever passes.
    """
    if not isinstance(payload, dict):
        raise ActionPayloadError() from None
    if set(payload) != {"schemaVersion", "action"}:
        raise ActionPayloadError() from None
    version = payload["schemaVersion"]
    if isinstance(version, bool) or not isinstance(version, int):
        raise ActionPayloadError() from None
    if version != REFRESH_SCHEMA_VERSION:
        raise ActionPayloadError() from None
    if payload["action"] != ACTION_REFRESH:
        raise ActionPayloadError() from None


def copy_command_is_eligible(availability: object, command: object) -> bool:
    """Copy is enabled only for a known action with an exact command.

    The rule mirrors the UI control: the next action's availability must
    be ``"known"`` and its copyableAgentCommand must be a non-empty
    string. A null, empty, or non-string value never enables copy, and
    no prose field (label, summary) may ever substitute for the command.
    """
    return (
        availability == "known"
        and isinstance(command, str)
        and command != ""
    )


# -- Diagnostic export payloads (ADR-0044, contract spec §4) -----------

_DIGEST_HEX_LENGTH = 64
_SNAPSHOT_DIGEST_PREFIX = "sha256:"


def _participant_ref_of(payload: dict) -> str | None:
    """Extract the optional participantRef or raise the closed rejection.

    The participant identifier is participant-supplied (ADR-0036 §8): a
    printable string of bounded length, echoed verbatim, never generated.
    A missing field is absent; an empty or malformed string is the typed
    rejection — nothing is invented in its place.
    """
    ref = payload.get("participantRef")
    if ref is None:
        return None
    if (
        not isinstance(ref, str)
        or not ref
        or len(ref) > 64
        or any(character in ref for character in "\r\n\t")
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in ref)
    ):
        raise ActionPayloadError() from None
    return ref


def _snapshot_digest_field(payload: dict, key: str) -> str:
    """A snapshot-form digest: exactly ``sha256:<64 lowercase hex>``."""
    value = payload.get(key)
    if not isinstance(value, str) or not value.startswith(_SNAPSHOT_DIGEST_PREFIX):
        raise ActionPayloadError() from None
    hex_part = value[len(_SNAPSHOT_DIGEST_PREFIX):]
    if (
        len(hex_part) != _DIGEST_HEX_LENGTH
        or any(character not in "0123456789abcdef" for character in hex_part)
    ):
        raise ActionPayloadError() from None
    return value


def _plain_digest_field(payload: dict, key: str) -> str:
    """A plain preview hash: exactly 64 lowercase hex characters."""
    value = payload.get(key)
    if (
        not isinstance(value, str)
        or len(value) != _DIGEST_HEX_LENGTH
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ActionPayloadError() from None
    return value


def validate_export_preview_payload(payload: object) -> str | None:
    """Accept exactly the closed export preview request (contract spec §4.1).

    ``{"schemaVersion": 1, "action": "diagnostic-export-preview"}`` plus an
    optional participant-supplied ``participantRef``. Any unknown field,
    missing field, type confusion, or malformed reference is the typed
    rejection.
    """
    if not isinstance(payload, dict):
        raise ActionPayloadError() from None
    allowed = {"schemaVersion", "action", "participantRef"}
    if not set(payload) <= allowed or not {"schemaVersion", "action"} <= set(payload):
        raise ActionPayloadError() from None
    version = payload["schemaVersion"]
    if isinstance(version, bool) or not isinstance(version, int):
        raise ActionPayloadError() from None
    if version != EXPORT_SCHEMA_VERSION:
        raise ActionPayloadError() from None
    if payload["action"] != ACTION_EXPORT_PREVIEW:
        raise ActionPayloadError() from None
    return _participant_ref_of(payload)


def validate_export_write_payload(payload: object) -> tuple[str, str, str | None]:
    """Accept exactly the closed export write request (contract spec §4.2).

    Returns ``(expectedSourceSetHash, previewHash, participantRef)``.
    ``participantReviewed`` must be the literal ``true`` — the explicit
    review acknowledgement; the field is required and nothing else passes.
    """
    if not isinstance(payload, dict):
        raise ActionPayloadError() from None
    allowed = {
        "schemaVersion",
        "action",
        "expectedSourceSetHash",
        "previewHash",
        "participantReviewed",
        "participantRef",
    }
    required = {
        "schemaVersion",
        "action",
        "expectedSourceSetHash",
        "previewHash",
        "participantReviewed",
    }
    if not set(payload) <= allowed or not required <= set(payload):
        raise ActionPayloadError() from None
    version = payload["schemaVersion"]
    if isinstance(version, bool) or not isinstance(version, int):
        raise ActionPayloadError() from None
    if version != EXPORT_SCHEMA_VERSION:
        raise ActionPayloadError() from None
    if payload["action"] != ACTION_EXPORT_WRITE:
        raise ActionPayloadError() from None
    if payload["participantReviewed"] is not True:
        raise ActionPayloadError() from None
    expected = _snapshot_digest_field(payload, "expectedSourceSetHash")
    preview = _plain_digest_field(payload, "previewHash")
    return expected, preview, _participant_ref_of(payload)


def _discard_cached_snapshot(session: RunConsoleSession) -> None:
    """Drop the session's cached snapshot so the next build is a rebuild.

    ``build_snapshot`` re-runs the full RCV1-005 pipeline and installs
    the registry and document only on success, so a failed rebuild
    surfaces the typed SnapshotBuildError instead of serving the prior
    snapshot as current.
    """
    session.invalidate_snapshot_cache()


def perform_refresh(session: RunConsoleSession) -> dict:
    """Run one full snapshot rebuild and return the new document.

    The session keeps its token and identity; the rebuilt registry and
    document replace the cached ones only when the build succeeds, so a
    failure raises the typed build error and the session never serves
    the pre-refresh snapshot as current afterwards.
    """
    if session.closed:
        raise RunConsoleSessionError(SESSION_CLOSED)
    # Keep invalidation and publication in one session-level critical
    # section.  Otherwise a second HTTP worker can rebuild between these two
    # calls and publish a document whose locators do not match the registry
    # currently used by source reads.
    return session.rebuild_snapshot()
