"""Closed typed-action allowlist for the run console (RCV1-009).

This module is the single source of truth for which typed capabilities
the run console exposes. The allowlist is closed: adding a capability
means editing this module and its tests together. There is no generic
dispatch — the HTTP layer wires exactly one server action route
(``POST /api/v1/actions/refresh``), the hash-bound source view is the
existing read route, and the copy capability is browser-only clipboard
work with no server execution route at all. Role attestation and
diagnostic export stay explicitly disabled, and every forbidden action
name (repair, rerun, provider, file edit, upload, ...) has no entry
here and no route anywhere.

Nothing in this module opens a socket, spawns a process, or writes to
the run tree: the only effect of the refresh action is one full
snapshot rebuild through the RCV1-005 seams.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Mapping

from .request_security import ACTION_PAYLOAD_INVALID
from .session import (
    SESSION_CLOSED,
    RunConsoleSession,
    RunConsoleSessionError,
)

# A code owned here (request_security.py is frozen outside this change):
# a non-JSON content type on the one action route is a 415, not a 400.
CONTENT_TYPE_UNSUPPORTED = "CONTENT_TYPE_UNSUPPORTED"
CONTENT_TYPE_UNSUPPORTED_MESSAGE = (
    "The typed action requires an application/json request body."
)

JSON_CONTENT_TYPE = "application/json"
ACTION_REFRESH = "refresh"
REFRESH_ROUTE = "/api/v1/actions/refresh"
REFRESH_ALLOWED_METHODS = "POST"
REFRESH_SCHEMA_VERSION = 1

# Capability kinds: a server action is dispatched by the HTTP layer; a
# read route already exists in http_server; a browser-only capability
# has no server execution route at all.
KIND_SERVER_ACTION = "server-action"
KIND_READ_ROUTE = "read-route"
KIND_BROWSER_ONLY = "browser-only"


@dataclass(frozen=True)
class Capability:
    """One entry of the closed allowlist."""

    name: str
    kind: str
    method: str | None
    route: str | None
    description: str


CAPABILITIES: tuple[Capability, ...] = (
    Capability(
        name=ACTION_REFRESH,
        kind=KIND_SERVER_ACTION,
        method="POST",
        route=REFRESH_ROUTE,
        description=(
            "One full snapshot rebuild, requested with the closed payload "
            '{"schemaVersion": 1, "action": "refresh"}.'
        ),
    ),
    Capability(
        name="view-source",
        kind=KIND_READ_ROUTE,
        method="GET",
        route="/api/v1/sources/<locator>?expectedHash=<sha256>",
        description=(
            "The existing hash-bound source view: an opaque locator plus "
            "the hash bound at build time, answered with a text excerpt."
        ),
    ),
    Capability(
        name="copy-agent-command",
        kind=KIND_BROWSER_ONLY,
        method=None,
        route=None,
        description=(
            "Browser-only clipboard copy of the exact owner-provided "
            "copyableAgentCommand of a known next action; the command is "
            "never run, never sent anywhere, and never synthesized."
        ),
    ),
)

CAPABILITY_BY_NAME: Mapping[str, Capability] = {
    capability.name: capability for capability in CAPABILITIES
}


def capability_names() -> tuple[str, ...]:
    """The closed allowlist, in registry order."""
    return tuple(capability.name for capability in CAPABILITIES)


class ActionPayloadError(ValueError):
    """A typed rejection of a body that is not the closed action payload."""

    def __init__(
        self, message: str = "The action payload is not the closed schema."
    ) -> None:
        super().__init__(message)
        self.code = ACTION_PAYLOAD_INVALID


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
    """Decode one UTF-8 JSON request body or raise the typed rejection."""
    if not isinstance(raw, (bytes, bytearray)):
        raise ActionPayloadError() from None
    try:
        return json.loads(bytes(raw).decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise ActionPayloadError() from None


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
    _discard_cached_snapshot(session)
    return session.build_snapshot()
