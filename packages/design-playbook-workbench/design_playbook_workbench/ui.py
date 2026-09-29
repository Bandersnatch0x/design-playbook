"""Frozen static UI bytes for the workbench shell (R01, R15).

The shell is a vanilla HTML/CSS/JS triple with no build step, no
framework, no remote asset, and no storage: the bytes are read once at
server construction, so nothing can change under a running service.
Only exact paths resolve -- there is no filesystem access at request
time, so traversal, encoded paths, and listing attempts have no surface.
The shell document is deliberately content-free: it carries no project
path, asset, or credential, because any process able to reach the
loopback port can fetch it without a session.
"""
from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

ROUTE_TO_FILE: dict[str, str] = {
    "/": "app.html",
    "/app.html": "app.html",
    "/app.css": "app.css",
    "/app.js": "app.js",
}

CONTENT_TYPES: dict[str, str] = {
    "app.html": "text/html; charset=utf-8",
    "app.css": "text/css; charset=utf-8",
    "app.js": "text/javascript; charset=utf-8",
}


def shell_policy(preview_origin: str | None = None) -> str:
    """The management shell policy.

    The shell may frame exactly one extra origin: the isolated preview
    origin, whose own policy keeps previewed content away from the
    management API. Without a preview origin nothing may be framed.
    """
    frame_src = preview_origin if preview_origin else "'none'"
    return (
        "default-src 'none'; style-src 'self'; script-src 'self'; "
        "connect-src 'self'; img-src 'self' data:; "
        f"frame-src {frame_src}; frame-ancestors 'none'; "
        "base-uri 'none'; form-action 'none'"
    )


CONTENT_SECURITY_POLICY: dict[str, str] = {
    "app.html": shell_policy(),
    "app.css": "default-src 'none'; frame-ancestors 'none'",
    "app.js": "default-src 'none'; frame-ancestors 'none'",
}


class StaticResource(NamedTuple):
    body: bytes
    content_type: str
    content_security_policy: str


class UIResources:
    """The workbench shell, frozen once per server instance."""

    def __init__(self, directory: Path | str | None = None) -> None:
        base = (
            Path(directory)
            if directory is not None
            else Path(__file__).resolve().parent / "web"
        )
        entries: dict[str, StaticResource] = {}
        for route, name in ROUTE_TO_FILE.items():
            entries[route] = StaticResource(
                body=(base / name).read_bytes(),
                content_type=CONTENT_TYPES[name],
                content_security_policy=CONTENT_SECURITY_POLICY[name],
            )
        self._entries = entries
        self.directory = base

    def set_preview_origin(self, origin: str) -> None:
        """Allow the shell to frame exactly this preview origin.

        Called once, before the first request is served: the served bytes
        are still frozen for the whole session lifetime.
        """
        entry = self._entries["/"]
        policy = shell_policy(origin)
        self._entries["/"] = entry._replace(content_security_policy=policy)
        self._entries["/app.html"] = self._entries["/app.html"]._replace(
            content_security_policy=policy
        )

    def lookup(self, path: object) -> StaticResource | None:
        if not isinstance(path, str):
            return None
        return self._entries.get(path)
