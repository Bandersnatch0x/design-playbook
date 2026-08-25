"""Pure request-security policy for the single-run read API (RCV1-006).

Snapshot v1 section 11.2 rules as pure, I/O-free functions: only the two
IP-literal loopback addresses may be bound (S24); the session bearer token
is presented only via ``Authorization: Bearer`` and compared in constant
time after basic validation, and never travels in a query string (S25);
the Host header must equal the exact bound authority and Origin must be
absent (reads) or exactly bound (S26); responses carry the restrictive
header policy with no CORS (S26); error codes and messages are fixed and
safe. No function here performs I/O or reads the environment.
"""
from __future__ import annotations

import hmac
import re

LOOPBACK_BIND_HOSTS: tuple[str, ...] = ("127.0.0.1", "::1")
DEFAULT_BIND_HOST = "127.0.0.1"

SESSION_TOKEN_INVALID = "SESSION_TOKEN_INVALID"
ORIGIN_INVALID = "ORIGIN_INVALID"
METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
REQUEST_TOO_LARGE = "REQUEST_TOO_LARGE"
ACTION_PAYLOAD_INVALID = "ACTION_PAYLOAD_INVALID"
ROUTE_NOT_FOUND = "ROUTE_NOT_FOUND"
SNAPSHOT_BUILD_FAILED = "SNAPSHOT_BUILD_FAILED"

ERROR_MESSAGES: dict[str, str] = {
    SESSION_TOKEN_INVALID: "The session token is missing or invalid.",
    ORIGIN_INVALID: "The request origin is not permitted.",
    METHOD_NOT_ALLOWED: "The request method is not allowed for this resource.",
    REQUEST_TOO_LARGE: "The request body is too large.",
    ACTION_PAYLOAD_INVALID: "The request parameters are invalid.",
    ROUTE_NOT_FOUND: "The requested resource does not exist.",
    SNAPSHOT_BUILD_FAILED: "The run snapshot could not be built.",
}

#: The one error code a consumer may safely retry after a refresh.
RETRYABLE_CODES = frozenset({"SOURCE_HASH_MISMATCH"})

_AUTHORIZATION_SCHEME = "Bearer"
# secrets.token_urlsafe(32) is 43 characters of this alphabet.
_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{32,256}$")
_EXPECTED_HASH_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_AUTH_QUERY_NAMES = frozenset(
    {
        "token",
        "access_token",
        "api_token",
        "api_key",
        "authorization",
        "session",
        "session_token",
        "auth",
        "key",
        "bearer",
        "password",
    }
)


def ensure_loopback_bind_host(host: object) -> str:
    """Return ``host`` iff it is one of the two IP-literal loopback hosts.

    Wildcards, LAN addresses, hostnames, bracketed forms, and non-strings
    are rejected (S24): the server may never bind anything but an
    IP-literal loopback address.
    """
    if not isinstance(host, str) or host not in LOOPBACK_BIND_HOSTS:
        raise ValueError(
            "bind host must be one of the IP-literal loopback addresses "
            "127.0.0.1 or ::1"
        )
    return host


def canonical_authority(bind_host: object, port: object) -> str:
    """The exact ``Host`` header value for the bound loopback listener."""
    host = ensure_loopback_bind_host(bind_host)
    if isinstance(port, bool) or not isinstance(port, int):
        raise ValueError("port must be an int")
    if not 0 < port < 65536:
        raise ValueError("port must be a valid TCP port")
    if ":" in host:
        return f"[{host}]:{port}"
    return f"{host}:{port}"


def canonical_origin(bind_host: object, port: object) -> str:
    """The exact ``Origin`` header value for the bound loopback listener."""
    return "http://" + canonical_authority(bind_host, port)


def host_header_is_valid(host: object, *, bind_host: str, port: int) -> bool:
    """True iff Host equals the exact bound loopback authority (S26).

    Missing, duplicated (non-string sentinel), wrong-host, wrong-port,
    schemed, and bracketed-IPv4 forms are all invalid.
    """
    if not isinstance(host, str):
        return False
    expected = canonical_authority(bind_host, port)
    return host.strip().lower() == expected


def origin_header_is_valid(
    origin: object, *, bind_host: str, port: int, read_only: bool
) -> bool:
    """True iff Origin satisfies the exact per-method rule (S26).

    GET/HEAD may omit Origin; any supplied Origin must equal the exact
    bound origin (a conflicting GET Origin is rejected). Every other
    method must present exactly the bound origin.
    """
    expected = canonical_origin(bind_host, port)
    if origin is None:
        return read_only
    if not isinstance(origin, str):
        return False
    return origin.strip() == expected


def extract_bearer_token(authorization: object) -> str | None:
    """Return the bearer token from a well-formed Authorization header.

    Anything else -- missing header, wrong scheme, extra spaces or
    parameters, or a token outside the basic length/charset bound --
    yields ``None`` before any comparison happens (S25).
    """
    if not isinstance(authorization, str):
        return None
    parts = authorization.strip().split(" ")
    if len(parts) != 2 or parts[0] != _AUTHORIZATION_SCHEME:
        return None
    token = parts[1]
    if _TOKEN_PATTERN.fullmatch(token) is None:
        return None
    return token


def token_is_valid(expected_token: object, presented_token: object) -> bool:
    """Constant-time bearer-token comparison after basic validation.

    Basic validation covers type, charset, and length only; the actual
    comparison is :func:`hmac.compare_digest`. A closed session has no
    expected token and every presentation fails.
    """
    if not isinstance(expected_token, str):
        return False
    if not isinstance(presented_token, str):
        return False
    if _TOKEN_PATTERN.fullmatch(presented_token) is None:
        return False
    if len(presented_token) != len(expected_token):
        return False
    return hmac.compare_digest(expected_token, presented_token)


def security_headers() -> dict[str, str]:
    """The fixed restrictive response header policy (S26).

    Content Security Policy with ``frame-ancestors 'none'``, nosniff, and
    no-store. No CORS header is ever part of the policy.
    """
    return {
        "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "no-store",
    }


def query_carries_auth_material(query: object) -> bool:
    """True iff the query string carries any credential-shaped parameter.

    The token must never travel in a query string (S25); such a
    presentation is treated as an invalid token, not ignored.
    """
    if not isinstance(query, str) or not query:
        return False
    for part in query.split("&"):
        name = part.split("=", 1)[0].strip().lower()
        if name in _AUTH_QUERY_NAMES:
            return True
    return False


def expected_hash_is_well_formed(value: object) -> bool:
    """True iff value is exactly ``sha256:<64 lowercase hex>``."""
    return isinstance(value, str) and _EXPECTED_HASH_PATTERN.fullmatch(value) is not None
