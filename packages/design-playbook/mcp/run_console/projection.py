"""Opaque source-locator resolver for the read-only Run Console boundary.

The Snapshot issues opaque ``src_`` locators through the session Source
registry (slice A); this module is the only resolver. It turns one live
locator binding into a bounded, plain-text, read-only excerpt of exactly
the bound source:

- the locator itself is looked up server-side through the registry, so
  unknown, malformed, expired, cross-session, and cross-run requests all
  collapse into one uniform ``SOURCE_LOCATOR_INVALID`` answer with no
  path, token, or containment detail;
- the bound target is re-read through the containment owner seam
  (``read_artifact`` under the evidence subtree, ``read_under`` for the
  run and package roots, ADR-0039), so traversal, absolute, encoded, and
  symlink-escaping targets read zero bytes outside the bound source;
- the current content is hashed exactly the way the Snapshot hashed it
  (raw bytes for artifacts, normalized decoded text for text sources)
  and compared with the hash bound into the locator: a changed source is
  ``SOURCE_HASH_MISMATCH`` and never returns a newer excerpt;
- the excerpt is HTML-escaped and hard-truncated, so source content can
  never carry executable markup or an unbounded payload across the seam.

The resolver writes nothing, opens no socket, and runs no process.
"""
from __future__ import annotations

import hashlib
import html
from dataclasses import dataclass
from pathlib import Path

from design_playbook.mcp.evidence.containment import read_artifact, read_under
from design_playbook.mcp.run_console.source_registry import (
    LocatorBinding,
    SourceRegistry,
)

SOURCE_LOCATOR_INVALID = "SOURCE_LOCATOR_INVALID"
SOURCE_HASH_MISMATCH = "SOURCE_HASH_MISMATCH"

_ERROR_MESSAGES = {
    SOURCE_LOCATOR_INVALID: "The source locator is not valid for this session.",
    SOURCE_HASH_MISMATCH: "The bound source changed; rebuild to view it.",
}

_DEFAULT_MAX_CHARS = 4000
_MAX_CHARS_LIMIT = 8192


class SourceViewError(ValueError):
    """Stable, path-free rejection at the source-view seam.

    One code and one fixed message per failure class; rejected input
    details never cross the seam.
    """

    def __init__(self, code: str) -> None:
        if code not in _ERROR_MESSAGES:
            raise ValueError("unknown source-view error code")
        super().__init__(_ERROR_MESSAGES[code])
        self.code = code


@dataclass(frozen=True)
class SourceExcerpt:
    """One bounded, plain, hash-checked excerpt of a bound source."""

    source_ref: str
    content_hash: str
    text: str


def resolve_source_excerpt(
    *,
    registry: SourceRegistry,
    package_root: Path,
    locator: object,
    now: str,
    max_chars: int = _DEFAULT_MAX_CHARS,
) -> SourceExcerpt:
    """Resolve one opaque locator into a read-only excerpt of its source.

    Every failure is one :class:`SourceViewError`; no failure message or
    exception attribute discloses the target, the path, or the request.
    """
    if not isinstance(registry, SourceRegistry):
        raise SourceViewError(SOURCE_LOCATOR_INVALID)
    binding = registry.lookup_locator(locator, now)
    if binding is None or not binding.target:
        # Unknown, malformed, expired, cross-session, cross-run, or a
        # composite source with no single file target: uniform rejection.
        raise SourceViewError(SOURCE_LOCATOR_INVALID)
    data = _read_bound_source(registry, package_root, binding)
    if data is None:
        # The bound target cannot be read through containment today.
        raise SourceViewError(SOURCE_LOCATOR_INVALID)
    if binding.source_ref.startswith("source.evidence-artifact."):
        # Evidence artifacts are the one byte-hashed source family: the
        # Snapshot hashed the captured artifact bytes themselves.
        digest = _digest_bytes(data)
        decoded = data.decode("utf-8", errors="replace")
    else:
        # Text sources are hashed over the same normalized decoded text
        # the Snapshot captured through the owner read seams.
        decoded = _normalize_newlines(data.decode("utf-8", errors="replace"))
        digest = _digest_text(decoded)
    if digest != binding.expected_hash:
        raise SourceViewError(SOURCE_HASH_MISMATCH)
    limit = max(1, min(int(max_chars), _MAX_CHARS_LIMIT))
    return SourceExcerpt(
        source_ref=binding.source_ref,
        content_hash=digest,
        # Escape first, then hard-truncate: the output is always plain
        # text and never longer than the requested bound.
        text=html.escape(decoded, quote=False)[:limit],
    )


def _digest_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _digest_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _normalize_newlines(text: str) -> str:
    """Reproduce the owner text reads' universal-newline translation."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _read_bound_source(
    registry: SourceRegistry, package_root: Path, binding: LocatorBinding
) -> bytes | None:
    """Read exactly the bound target, or ``None`` if containment fails."""
    target = binding.target
    if not isinstance(target, str) or not target:
        return None
    if target.startswith("evidence/"):
        # Evidence artifacts (and the Manifest itself) go through the
        # evidence containment seam: symlink and canonical escapes, missing
        # files, and traversal are rejected before any byte is read.
        result = read_artifact(target, registry.selected_root)
    else:
        # Run-root and package-root sources go through the same owner's
        # generalized read primitive (ADR-0039): one resolver, one set of
        # escape classes, no local mirror.
        root = package_root if binding.kind == "package" else registry.selected_root
        result = read_under(root, target)
    if not result.ok or result.path is None:
        return None
    try:
        return result.path.read_bytes()
    except OSError:
        return None
