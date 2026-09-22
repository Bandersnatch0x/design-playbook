#!/usr/bin/env python3
"""Single Evidence artifact containment authority (ADR-0026, ADR-0039).

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

ADR-0039 extends the same invariant to arbitrary roots: ``read_under``
exposes the canonical resolution for one existing regular file under any
directory, and the Run Console's source reads (run root, package root)
consume it instead of mirroring the escape classes. The ``evidence/``
operations remain the ADR-0026 contract surface - same reason codes, same
existence timing - now expressed as specializations of the one resolver.

ADR-0044 adds the Diagnostic export write boundary as a third specialization:
``trial_export_write_target`` confines one bare filename under
``<run_root>/trial-export/`` (the trial-export subtree), with the same
reason-code discipline and TOCTOU limit.

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
# Trial-export targets (ADR-0044) accept bare filenames only; a name that
# carries any separator or reserved form is rejected before resolution.
REASON_RESERVED_NAME = "reserved_name"

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


def _resolve_candidate(
        candidate_root: Path,
        relpath: str,
        boundary_root: Path,
        *,
        require_existing_file: bool) -> ContainmentResult:
    """Canonical containment resolution shared by every operation here.

    ``relpath`` joins ``candidate_root`` to form the candidate; the resolved
    candidate (and its realpath) must stay under ``boundary_root``. The
    evidence operations pass the run root as the candidate root and the
    evidence subtree as the boundary (their paths are run-root-relative,
    including the ``evidence/`` prefix); ``read_under`` passes the same root
    for both.

    Rejects, in order: native/POSIX/Windows absolute paths; any ``..``
    segment (defence in depth before resolution); resolution failures
    (OSError during resolve); canonical escapes (resolved candidate leaves
    the boundary root); observed symlink escapes (realpath leaves the
    boundary root - Path.resolve and os.path.realpath can disagree on
    symlink chains across platforms). When ``require_existing_file`` is set,
    a candidate that is not an existing regular file is rejected last.
    """
    requested = Path(relpath)

    # 1. Absolute path rejection: native, POSIX, and Windows forms. Checking
    #    all three means a Windows drive path is rejected on POSIX and a POSIX
    #    root path is rejected on Windows, regardless of the host's native
    #    Path flavour.
    if (
        requested.is_absolute()
        or PureWindowsPath(relpath).is_absolute()
        or PurePosixPath(relpath).is_absolute()
    ):
        return ContainmentResult(None, REASON_ABSOLUTE_PATH)

    # 2. ``..`` segment rejection (defence in depth before resolution). Also
    #    catches ``evidence/../spec.md`` without relying on the resolver.
    if any(part == ".." for part in requested.parts):
        return ContainmentResult(None, REASON_DOTDOT_SEGMENT)

    # 3. Resolution. Both the boundary root and the candidate are resolved
    #    here; an OSError (e.g. a pathological symlink chain on a platform
    #    whose resolver raises) is caught and surfaced as a resolution
    #    failure rather than propagated.
    try:
        boundary = boundary_root.resolve(strict=False)
        candidate = (candidate_root / requested).resolve(strict=False)
    except OSError:
        return ContainmentResult(None, REASON_RESOLUTION_FAILURE)

    # 4. Canonical escape: the resolved candidate must stay under the
    #    boundary root. For the evidence operations this catches ``spec.md``
    #    and ``skills/x`` (siblings of evidence/).
    try:
        candidate.relative_to(boundary)
    except ValueError:
        return ContainmentResult(None, REASON_CANONICAL_ESCAPE)

    # 5. Symlink escape (defence in depth): realpath must also stay under the
    #    boundary root. Path.resolve and os.path.realpath can disagree on
    #    symlink chains across platforms, so a symlink under the boundary
    #    that resolves outside must be rejected even when step 4 passed.
    try:
        Path(os.path.realpath(candidate)).relative_to(os.path.realpath(boundary))
    except ValueError:
        return ContainmentResult(None, REASON_SYMLINK_ESCAPE)

    # 6. Read side: require an existing regular file. The write side permits
    #    a nonexistent suffix and stops here (the Provider's manifest-refusal
    #    and overwrite checks are separate policy, not containment).
    if require_existing_file and not candidate.is_file():
        return ContainmentResult(None, REASON_NOT_REGULAR_FILE)

    return ContainmentResult(candidate, "")


def _resolve(
        artifact_path: str,
        run_root: Path,
        *,
        require_existing_file: bool) -> ContainmentResult:
    """Resolve an evidence artifact path (run-root-relative) under evidence/."""
    return _resolve_candidate(
        run_root,
        artifact_path,
        run_root / EVIDENCE_SUBDIR,
        require_existing_file=require_existing_file,
    )


def read_under(root: Path, relpath: str) -> ContainmentResult:
    """Resolve one existing regular file under an arbitrary root (ADR-0039).

    The same escape classes as the evidence operations, for callers whose
    authority root is not the evidence subtree (Run Console source reads
    under the selected run root or the package root). ``relpath`` is
    root-relative. Resolution-only, same TOCTOU limit as above.
    """
    return _resolve_candidate(
        root, relpath, root, require_existing_file=True
    )


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


# The Diagnostic export write boundary (ADR-0044): one subtree, sibling of
# evidence/, owned here so the export transaction cannot disagree with the
# one containment authority on where trial exports may land.
TRIAL_EXPORT_SUBDIR = "trial-export"

# Names the export subtree may never carry. ``manifest.jsonl`` is reserved
# across the run tree (the Evidence Manifest authority); the current-directory
# name is a no-op write and is refused as malformed rather than silently
# permitted.
_TRIAL_EXPORT_RESERVED_NAMES = frozenset({"manifest.jsonl", "", ".", ".."})

# Win32 name quirks that CreateFile folds but Path.resolve does not: a
# trailing dot or space vanishes on write (the on-disk name would diverge
# from the reviewed one), and the reserved device names are never regular
# files. The export writes exactly the reviewed pair, so both classes are
# rejected as reserved.
_WIN32_DEVICE_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL",
     *(f"COM{i}" for i in range(1, 10)),
     *(f"LPT{i}" for i in range(1, 10))},
)


def trial_export_write_target(filename: str, run_root: Path) -> ContainmentResult:
    """Resolve a Diagnostic export write target under ``trial-export/``.

    ``filename`` must be a bare filename - no directory separators (native,
    POSIX, or Windows), no drive form, no ``..`` segment, and not one of the
    reserved names, Win32 fold forms (trailing dot or space), or reserved
    device stems - anything the platform would write under a different name
    than the one reviewed. Same resolution-time escape
    rejection and TOCTOU limit as every operation in this module; the
    transaction performs the staged write and rollback around this resolution.
    """
    if not isinstance(filename, str) or filename == "":
        return ContainmentResult(None, REASON_RESERVED_NAME)
    if filename in _TRIAL_EXPORT_RESERVED_NAMES:
        return ContainmentResult(None, REASON_RESERVED_NAME)
    # Bare-filename precondition: any separator, drive, or traversal form
    # fails before the generic resolver can even see it.
    if (
        PurePosixPath(filename).is_absolute()
        or PureWindowsPath(filename).is_absolute()
        or "/" in filename
        or "\\" in filename
        or any(part == ".." for part in PurePosixPath(filename).parts)
        or any(part == ".." for part in PureWindowsPath(filename).parts)
        or ":" in filename
    ):
        return ContainmentResult(None, REASON_ABSOLUTE_PATH)
    # Win32 fold classes: a trailing dot/space or a reserved device stem
    # would make the on-disk name differ from the reviewed name.
    if filename != filename.rstrip(" ."):
        return ContainmentResult(None, REASON_RESERVED_NAME)
    if filename.split(".", 1)[0].upper() in _WIN32_DEVICE_NAMES:
        return ContainmentResult(None, REASON_RESERVED_NAME)
    # The boundary subtree itself must be a real child of the run root: a
    # ``trial-export`` symlink pointing outside the run root would make the
    # generic under-boundary check pass while writing outside the selected
    # run, so the resolved boundary is required to stay inside the resolved
    # run root before anything else is resolved against it.
    try:
        resolved_root = run_root.resolve(strict=False)
        boundary = (run_root / TRIAL_EXPORT_SUBDIR).resolve(strict=False)
        Path(os.path.realpath(boundary)).relative_to(
            Path(os.path.realpath(resolved_root))
        )
    except (OSError, ValueError):
        return ContainmentResult(None, REASON_SYMLINK_ESCAPE)
    result = _resolve_candidate(
        run_root,
        f"{TRIAL_EXPORT_SUBDIR}/{filename}",
        run_root / TRIAL_EXPORT_SUBDIR,
        require_existing_file=False,
    )
    # The generic resolver also folds "." segments; a name like "a/." or
    # "a.." is a file name here, but a name that Path normalizes to
    # something other than itself inside the subtree must not pass.
    if result.ok and result.path is not None and result.path.name != filename:
        return ContainmentResult(None, REASON_RESERVED_NAME)
    return result
