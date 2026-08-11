#!/usr/bin/env python3
"""Single Evidence artifact containment authority (ADR-0026).

This is the one deep module that resolves an artifact path under
``<run_root>/evidence/`` and rejects every escape class at resolution time.
It exposes two distinct operations - ``write_target`` (permits a nonexistent
suffix; checks the existing resolved prefix) and ``read_artifact``
(additionally requires an existing regular file) - backed by one private
canonical containment implementation and stable failure reason codes.

The Provider (``mcp.evidence.server._resolve_artifact_path``) and G6
(``scripts.g6_evidence.check_evidence``) previously enforced the same
security invariant with separate implementations. They now map this module's
reason codes to their existing payloads, rule IDs, messages, and repair text
without re-checking containment. Collapsing both callers into one mode-driven
helper was rejected because it would hide their different existence timing
and error contracts (ADR-0026).

Threat-model limit (ADR-0026, explicit): this module resolves and validates
the path; it does NOT perform the write. Path resolution alone cannot close
the TOCTOU gap - a concurrent untrusted filesystem actor that replaces a
parent directory or symlink between resolution and the caller's write can
defeat containment. Callers must not add another preflight check. If that
threat enters scope, the actual write must move behind a directory-handle-
based or equivalent containment-preserving primitive owned here.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

# The evidence subtree name. Owned here so the write and read sides cannot
# disagree on what the containment boundary is.
EVIDENCE_SUBDIR = "evidence"

# Stable reason codes (ADR-0026). Both operations return one of these on
# failure; the Provider and G6 map them to their existing payloads. These
# strings are the contract - a rename is a visible break for both callers.
REASON_ABSOLUTE_PATH = "absolute_path"
REASON_DOTDOT_SEGMENT = "dotdot_segment"
REASON_RESOLUTION_FAILURE = "resolution_failure"
REASON_CANONICAL_ESCAPE = "canonical_escape"
REASON_SYMLINK_ESCAPE = "symlink_escape"
REASON_NOT_REGULAR_FILE = "not_regular_file"

# Every resolution-time escape reason (the classes the ADR requires both
# operations to reject at resolution time). The Provider treats all of these
# as a failed capture; G6 projects all of them as G6.escape.
RESOLUTION_ESCAPE_REASONS = frozenset({
    REASON_ABSOLUTE_PATH,
    REASON_DOTDOT_SEGMENT,
    REASON_RESOLUTION_FAILURE,
    REASON_CANONICAL_ESCAPE,
    REASON_SYMLINK_ESCAPE,
})


@dataclass(frozen=True)
class ContainmentResult:
    """Outcome of a containment resolution.

    ``path`` is the resolved absolute path on success and ``None`` on failure.
    ``reason`` is the empty string on success and one of the ``REASON_*``
    codes on failure. ``ok`` is True iff ``reason`` is empty.
    """

    path: Path | None
    reason: str = ""

    @property
    def ok(self) -> bool:
        return self.reason == ""


def _resolve(
        artifact_path: str,
        run_root: Path,
        *,
        require_existing_file: bool) -> ContainmentResult:
    """Canonical containment resolution shared by write_target and read_artifact.

    Rejects, in order: native/POSIX/Windows absolute paths; any ``..``
    segment (defence in depth before resolution); resolution failures
    (OSError during resolve); canonical escapes (resolved candidate leaves
    the evidence/ subtree); observed symlink escapes (realpath leaves the
    evidence/ subtree - Path.resolve and os.path.realpath can disagree on
    symlink chains across platforms). When ``require_existing_file`` is set,
    a candidate that is not an existing regular file is rejected last.
    """
    requested = Path(artifact_path)

    # 1. Absolute path rejection: native, POSIX, and Windows forms. Checking
    #    all three means a Windows drive path is rejected on POSIX and a POSIX
    #    root path is rejected on Windows, regardless of the host's native
    #    Path flavour.
    if (
        requested.is_absolute()
        or PureWindowsPath(artifact_path).is_absolute()
        or PurePosixPath(artifact_path).is_absolute()
    ):
        return ContainmentResult(None, REASON_ABSOLUTE_PATH)

    # 2. ``..`` segment rejection (defence in depth before resolution). Also
    #    catches ``evidence/../spec.md`` without relying on the resolver.
    if any(part == ".." for part in requested.parts):
        return ContainmentResult(None, REASON_DOTDOT_SEGMENT)

    # 3. Resolution. Both the evidence root and the candidate are resolved
    #    here; an OSError (e.g. a pathological symlink chain on a platform
    #    whose resolver raises) is caught and surfaced as a resolution
    #    failure rather than propagated.
    try:
        evidence_root = (run_root / EVIDENCE_SUBDIR).resolve(strict=False)
        candidate = (run_root / requested).resolve(strict=False)
    except OSError:
        return ContainmentResult(None, REASON_RESOLUTION_FAILURE)

    # 4. Canonical escape: the resolved candidate must stay under the evidence
    #    root. Catches ``spec.md`` and ``skills/x`` (siblings of evidence/).
    try:
        candidate.relative_to(evidence_root)
    except ValueError:
        return ContainmentResult(None, REASON_CANONICAL_ESCAPE)

    # 5. Symlink escape (defence in depth): realpath must also stay under the
    #    evidence root. Path.resolve and os.path.realpath can disagree on
    #    symlink chains across platforms, so a symlink under evidence/ that
    #    resolves outside must be rejected even when step 4 passed.
    try:
        Path(os.path.realpath(candidate)).relative_to(
            os.path.realpath(evidence_root)
        )
    except ValueError:
        return ContainmentResult(None, REASON_SYMLINK_ESCAPE)

    # 6. Read side: require an existing regular file. The write side permits a
    #    nonexistent suffix and stops here (the Provider's manifest-refusal
    #    and overwrite checks are separate policy, not containment).
    if require_existing_file and not candidate.is_file():
        return ContainmentResult(None, REASON_NOT_REGULAR_FILE)

    return ContainmentResult(candidate, "")


def write_target(artifact_path: str, run_root: Path) -> ContainmentResult:
    """Resolve a write target under ``<run_root>/evidence/``.

    Permits a nonexistent suffix (the Provider writes the file after this
    resolves) and checks the existing resolved prefix stays under the evidence
    subtree. Does NOT perform the write - see the TOCTOU threat-model limit
    in this module's docstring.
    """
    return _resolve(artifact_path, run_root, require_existing_file=False)


def read_artifact(artifact_path: str, run_root: Path) -> ContainmentResult:
    """Resolve an existing artifact under ``<run_root>/evidence/``.

    Applies every resolution-time escape rejection and additionally requires
    the candidate to be an existing regular file (G6 reads bound evidence and
    must not bind a directory or a missing path).
    """
    return _resolve(artifact_path, run_root, require_existing_file=True)
