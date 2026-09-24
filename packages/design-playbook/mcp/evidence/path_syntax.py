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


def probe_sidecar_rel(artifact_rel: str) -> str:
    """Sibling ``.probe.json`` path for a screenshot artifact path.

    Shared by the capture runtime (which writes it) and the static preflight
    (which must predict it to detect same-stem collisions). One definition so
    the two surfaces cannot drift.
    """
    if "." in artifact_rel.rsplit("/", 1)[-1]:
        return artifact_rel.rsplit(".", 1)[0] + ".probe.json"
    return artifact_rel + ".probe.json"


# On-disk shape of an interaction trace (DEF-6): ``tracing.stop(path=...)``
# writes a Playwright trace ZIP, so any other extension mislabels binary bytes.
TRACE_SUFFIX = ".zip"
TRACE_EXAMPLE = "evidence/<criterion>.trace.zip"


def trace_artifact_error(capture_type: str, artifact_rel: str) -> str:
    """Naming error when a trace capture is not named ``.zip``; "" otherwise.

    One definition for the capture runtime (hard reject) and the static
    preflight (early fact), so a plan never passes preflight only to fail there.
    An empty name is left to the required-field check at each call site.
    """
    if (
        capture_type == "interaction trace"
        and artifact_rel
        and not artifact_rel.casefold().endswith(TRACE_SUFFIX)
    ):
        return (
            "interaction trace artifacts are Playwright trace ZIP files — name "
            f"artifact_path with a {TRACE_SUFFIX} extension (e.g. {TRACE_EXAMPLE}); "
            f"got {artifact_rel!r}"
        )
    return ""
