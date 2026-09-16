"""Pure path-shape helpers shared by preflight and capture runtime.

No filesystem I/O. ``..`` stays a hard reject at each call site before these
helpers are used for collision keys.
"""
from __future__ import annotations


def trimmed_relpath(path: str) -> str:
    """Whitespace-normalise a relative path the way capture does before resolve."""
    return path.strip()


def lexical_posix_key(path: str) -> str:
    """Collision key: trim, drop empty and ``.`` segments, keep original ``..``.

    Does not resolve, stat, or follow links. Callers that already rejected
    ``..`` can use the result as a seen-key.
    """
    parts = [part for part in trimmed_relpath(path).split("/") if part not in ("", ".")]
    return "/".join(parts)
