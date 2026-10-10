"""Immutable static UI resources for the read-only Run Console (RCV1-007).

The Console UI is a vanilla HTML/CSS/JS triple with no build step, no
framework, no remote asset, and no storage. ``UIResources`` freezes the
three files into memory once at server construction: the exact bytes
served for the whole session lifetime are decided before the first
request, so no later filesystem change can alter what the operator's
browser receives. Route lookup is a fixed exact-path whitelist — there
is no filesystem access at request time, so traversal, encoded paths,
case games, and listing attempts have no surface: any path that is not
one of the five keys is simply not a UI route. ``/tokens.css`` is the
shared token file in ``mcp/_shared``, read from the package, not from the
UI directory.

The shell document needs a stricter-than-API CSP that still permits its
own same-origin stylesheet, script, and ``fetch`` calls; CSS and JS
assets get ``default-src 'none'`` like every other response.
"""
from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

#: URL path -> file name. Exactly these five paths are UI routes.
ROUTE_TO_FILE: dict[str, str] = {
    "/": "app.html",
    "/app.html": "app.html",
    "/tokens.css": "tokens.css",
    "/app.css": "app.css",
    "/app.js": "app.js",
}

#: The shared token file every own surface reads (U-07).
SHARED_TOKENS = Path(__file__).resolve().parent.parent / "_shared" / "tokens.css"

CONTENT_TYPES: dict[str, str] = {
    "app.html": "text/html; charset=utf-8",
    "tokens.css": "text/css; charset=utf-8",
    "app.css": "text/css; charset=utf-8",
    "app.js": "text/javascript; charset=utf-8",
}

#: The shell may load its own stylesheet/script and call the same-origin
#: read API; nothing else. Assets themselves allow no loads at all.
CONTENT_SECURITY_POLICY: dict[str, str] = {
    "app.html": (
        "default-src 'none'; style-src 'self'; script-src 'self'; "
        "connect-src 'self'; frame-ancestors 'none'; "
        "base-uri 'none'; form-action 'none'"
    ),
    "tokens.css": "default-src 'none'; frame-ancestors 'none'",
    "app.css": "default-src 'none'; frame-ancestors 'none'",
    "app.js": "default-src 'none'; frame-ancestors 'none'",
}


class StaticResource(NamedTuple):
    """One frozen response: bytes, media type, and CSP."""

    body: bytes
    content_type: str
    content_security_policy: str


class UIResources:
    """The Console UI bytes, frozen once per server instance."""

    def __init__(self, directory: Path | str | None = None) -> None:
        base = Path(directory) if directory is not None else Path(__file__).resolve().parent
        entries: dict[str, StaticResource] = {}
        for route, name in ROUTE_TO_FILE.items():
            source = SHARED_TOKENS if name == "tokens.css" else base / name
            body = source.read_bytes()
            entries[route] = StaticResource(
                body=body,
                content_type=CONTENT_TYPES[name],
                content_security_policy=CONTENT_SECURITY_POLICY[name],
            )
        self._entries = entries
        self.directory = base

    def lookup(self, path: object) -> StaticResource | None:
        """The frozen resource for an exact UI path, else ``None``.

        Only exact string matches against the five fixed routes resolve;
        every other input (unknown path, trailing slash, encoded bytes,
        non-string) is ``None`` and therefore not a UI route.
        """
        if not isinstance(path, str):
            return None
        return self._entries.get(path)
