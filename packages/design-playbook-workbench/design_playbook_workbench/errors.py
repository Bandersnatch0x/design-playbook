"""Typed, secret-free error envelope for the Workbench API v1.

Every rejection carries one code from the closed set below, a message
that never contains a filesystem path, credential, or traceback, and a
``retryable`` flag. Handlers raise :class:`WorkbenchError`; the HTTP
layer is the only place that turns it into a response, so no module
invents its own status mapping.

The unauthorized, origin-invalid, invalid-target, and disconnected codes
stay fully generic; a ``detail`` that only echoes what the caller itself
sent, and is identical whichever reason applied, does not weaken that.
"""
from __future__ import annotations

SCHEMA_VERSION = 1

# Domain codes (spec "公共契约表"): the minimum set every entry point must
# be able to express.
UNAUTHORIZED = "unauthorized"
INVALID_TARGET = "invalid-target"
DISCONNECTED = "disconnected"
CONFLICT = "conflict"
INVALID_INPUT = "invalid-input"
UNSUPPORTED = "unsupported"
LIMIT_EXCEEDED = "limit-exceeded"
MISSING_DEPENDENCY = "missing-dependency"
CORRUPT_CONTENT = "corrupt-content"
STALE_EVIDENCE = "stale-evidence"
OWNER_UNAVAILABLE = "owner-unavailable"
RECOVERY_REQUIRED = "recovery-required"

# Transport-level codes: request rejected before any domain rule ran.
ORIGIN_INVALID = "origin-invalid"
ROUTE_NOT_FOUND = "route-not-found"
METHOD_NOT_ALLOWED = "method-not-allowed"
REQUEST_TOO_LARGE = "request-too-large"
INTERNAL_ERROR = "internal-error"

MESSAGES: dict[str, str] = {
    UNAUTHORIZED: "The request is not authorized for this operation.",
    INVALID_TARGET: "The selected folder cannot be a project target.",
    DISCONNECTED: "The project folder is not currently reachable.",
    CONFLICT: "The request conflicts with the current state.",
    INVALID_INPUT: "The request parameters are invalid.",
    UNSUPPORTED: "The requested operation is not supported.",
    LIMIT_EXCEEDED: "The request exceeds a documented limit.",
    MISSING_DEPENDENCY: "A required dependency is missing.",
    CORRUPT_CONTENT: "Stored content failed its integrity check.",
    STALE_EVIDENCE: "The referenced evidence is stale.",
    OWNER_UNAVAILABLE: "The owning component is unavailable.",
    RECOVERY_REQUIRED: "A previous write needs recovery before new writes.",
    ORIGIN_INVALID: "The request origin or host is not permitted.",
    ROUTE_NOT_FOUND: "The requested resource does not exist.",
    METHOD_NOT_ALLOWED: "The request method is not allowed for this resource.",
    REQUEST_TOO_LARGE: "The request body is too large.",
    INTERNAL_ERROR: "The request failed before any state change.",
}

STATUS_BY_CODE: dict[str, int] = {
    UNAUTHORIZED: 401,
    ORIGIN_INVALID: 403,
    ROUTE_NOT_FOUND: 404,
    METHOD_NOT_ALLOWED: 405,
    INVALID_TARGET: 400,
    INVALID_INPUT: 400,
    UNSUPPORTED: 400,
    CONFLICT: 409,
    DISCONNECTED: 409,
    STALE_EVIDENCE: 409,
    LIMIT_EXCEEDED: 413,
    REQUEST_TOO_LARGE: 413,
    MISSING_DEPENDENCY: 422,
    CORRUPT_CONTENT: 422,
    OWNER_UNAVAILABLE: 503,
    RECOVERY_REQUIRED: 503,
    INTERNAL_ERROR: 500,
}

#: Codes a consumer may safely repeat with the same operation ID.
RETRYABLE_CODES = frozenset({OWNER_UNAVAILABLE, RECOVERY_REQUIRED, CONFLICT})


class WorkbenchError(Exception):
    """One typed, path-free rejection."""

    def __init__(
        self,
        code: str,
        *,
        detail: str | None = None,
        operation_id: str | None = None,
    ) -> None:
        if code not in MESSAGES:
            raise ValueError("unknown workbench error code")
        message = MESSAGES[code]
        if detail:
            message = f"{message} {detail}"
        super().__init__(message)
        self.code = code
        self.detail = detail
        self.operation_id = operation_id

    @property
    def status(self) -> int:
        return STATUS_BY_CODE[self.code]

    @property
    def retryable(self) -> bool:
        return self.code in RETRYABLE_CODES

    def envelope(self) -> dict:
        """The fixed error envelope; no path, secret, or traceback."""
        error: dict[str, object] = {
            "code": self.code,
            "message": str(self),
            "retryable": self.retryable,
        }
        if self.operation_id is not None:
            error["operationId"] = self.operation_id
        return {"schemaVersion": SCHEMA_VERSION, "error": error}
