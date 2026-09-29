"""Pure request-security policy for the Workbench API (R01).

I/O-free rules: only the two IP-literal loopback addresses are bindable;
the ``Host`` header must equal the exact bound authority; a browser write
must present the exact bound ``Origin`` while a read may omit it; a
non-browser slash capability must present **no** Origin at all, so a
missing Origin can never stand in for authentication; the session bearer
token and the capability token are compared in constant time and never
travel in a query string; every response carries the restrictive header
policy with no CORS.
"""
from __future__ import annotations

import hmac
import re

LOOPBACK_BIND_HOSTS: tuple[str, ...] = ("127.0.0.1", "::1")
DEFAULT_BIND_HOST = "127.0.0.1"

READ_METHODS = frozenset({"GET", "HEAD"})

_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{32,256}$")
_AUTHORIZATION_SCHEME = "Bearer"

_AUTH_QUERY_NAMES = frozenset(
    {
        "token",
        "access_token",
        "api_token",
        "api_key",
        "authorization",
        "session",
        "session_token",
        "bootstrap",
        "auth",
        "key",
        "bearer",
        "password",
        "capability",
    }
)


def ensure_loopback_bind_host(host: object) -> str:
    """Return ``host`` iff it is one of the two IP-literal loopback hosts."""
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
    """True iff ``Host`` equals the exact bound loopback authority."""
    if not isinstance(host, str):
        return False
    return host.strip().lower() == canonical_authority(bind_host, port)


def origin_header_is_valid(
    origin: object,
    *,
    bind_host: str,
    port: int,
    read_only: bool,
    capability: bool = False,
) -> bool:
    """True iff ``Origin`` satisfies the exact per-method rule.

    A capability-authenticated request must present no Origin at all: a
    browser would send one, so its absence is what distinguishes the
    non-browser slash path. Reads may omit Origin; writes must present
    exactly the bound origin.
    """
    if capability:
        return origin is None
    expected = canonical_origin(bind_host, port)
    if origin is None:
        return read_only
    if not isinstance(origin, str):
        return False
    return origin.strip() == expected


def extract_bearer_token(authorization: object) -> str | None:
    """The bearer token from a well-formed ``Authorization`` header."""
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
    """Constant-time token comparison after basic validation."""
    if not isinstance(expected_token, str) or not isinstance(presented_token, str):
        return False
    if _TOKEN_PATTERN.fullmatch(presented_token) is None:
        return False
    if len(presented_token) != len(expected_token):
        return False
    return hmac.compare_digest(expected_token, presented_token)


def capability_header_value(raw: object) -> str | None:
    """Validate a presented capability token (same shape as a session token)."""
    if not isinstance(raw, str):
        return None
    token = raw.strip()
    if _TOKEN_PATTERN.fullmatch(token) is None:
        return None
    return token


def query_carries_auth_material(query: object) -> bool:
    """True iff the query string carries any credential-shaped parameter."""
    if not isinstance(query, str) or not query:
        return False
    for part in query.split("&"):
        name = part.split("=", 1)[0].strip().lower()
        if name in _AUTH_QUERY_NAMES:
            return True
    return False


def security_headers() -> dict[str, str]:
    """The fixed restrictive response header policy (no CORS, no caching)."""
    return {
        "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "no-store",
        "Referrer-Policy": "no-referrer",
    }


def is_read_method(method: object) -> bool:
    return isinstance(method, str) and method.upper() in READ_METHODS
