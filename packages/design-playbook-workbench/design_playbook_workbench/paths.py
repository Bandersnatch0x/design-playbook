"""Canonical folder targets and directory identity (R02, R14).

Path is never identity: the canonical absolute path plus the directory
identity (device + file index) are both recorded, and both are rechecked
on every operation. A symlink or Windows junction is resolved before any
decision, so an alias can never bypass the duplicate-path rule or the
data-directory isolation rule, and an identity change (folder replaced,
moved, or re-pointed) is reported as disconnected rather than silently
re-matched by name.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

from .errors import INVALID_TARGET, WorkbenchError

CANDIDATE_PREFIX = "cand_"


@dataclass(frozen=True)
class FolderCandidate:
    """One confirmed-once folder target: path, identity, and binding token."""

    canonical_path: str
    directory_identity: str
    candidate_id: str
    suggested_name: str
    default_scope: str = "read"

    def as_payload(self) -> dict:
        return {
            "canonicalPath": self.canonical_path,
            "directoryIdentity": self.directory_identity,
            "candidateId": self.candidate_id,
            "suggestedName": self.suggested_name,
            "defaultScope": self.default_scope,
            "note": (
                "Registration grants read-only discovery. Write, execute, "
                "and model-send must each be granted separately."
            ),
        }


def _as_path(value: object) -> Path:
    if isinstance(value, str):
        if not value.strip():
            raise WorkbenchError(INVALID_TARGET)
        return Path(value)
    if isinstance(value, Path):
        return value
    raise WorkbenchError(INVALID_TARGET)


def is_remote_path(value: object) -> bool:
    """True for UNC/network paths, which are never a local project target."""
    text = str(value)
    return text.startswith("\\\\") or text.startswith("//")


def canonical_directory(value: object) -> Path:
    """Resolve one existing directory to its canonical absolute path.

    Relative input, a missing path, a file, a remote path, and any path
    the process cannot resolve are the same uniform invalid-target
    rejection: the caller learns nothing about what exists where.
    """
    candidate = _as_path(value)
    if is_remote_path(candidate):
        raise WorkbenchError(INVALID_TARGET)
    if not candidate.is_absolute():
        raise WorkbenchError(INVALID_TARGET)
    try:
        canonical = candidate.resolve(strict=True)
    except OSError:
        raise WorkbenchError(INVALID_TARGET) from None
    if not canonical.is_dir():
        raise WorkbenchError(INVALID_TARGET)
    return canonical


def directory_identity(path: Path | str) -> str:
    """``device:file-index`` for one resolved directory.

    ``st_ino`` is populated on Windows for directories (file index), and
    ``st_dev`` distinguishes volumes, so a replace-with-junction or a
    move to another volume changes the identity.
    """
    try:
        stat = os.stat(path)
    except OSError:
        raise WorkbenchError(INVALID_TARGET) from None
    if not os.path.isdir(path):
        raise WorkbenchError(INVALID_TARGET)
    return f"{stat.st_dev}:{stat.st_ino}"


def is_within(child: Path | str, parent: Path | str) -> bool:
    """True iff ``child`` is ``parent`` or lies below it (canonical paths)."""
    child_path = Path(child)
    parent_path = Path(parent)
    try:
        child_path.relative_to(parent_path)
    except ValueError:
        return False
    return True


def candidate_id_for(canonical_path: str, identity: str) -> str:
    """Binding token so a confirmation cannot drift from what was probed."""
    digest = hashlib.sha256(
        f"{canonical_path}\n{identity}".encode("utf-8")
    ).hexdigest()
    return CANDIDATE_PREFIX + digest[:32]


def _is_filesystem_root(path: Path) -> bool:
    return path.parent == path


def validate_folder_target(value: object, *, data_dir: Path | str) -> FolderCandidate:
    """Probe one maintainer-supplied absolute folder into a candidate.

    Rejects non-local, relative, missing, file, filesystem-root, and
    user-home-root targets, and every target that contains or is
    contained by the workbench data directory (R14: the data directory
    must never sit inside an imported source tree, or vice versa).
    """
    canonical = canonical_directory(value)
    if _is_filesystem_root(canonical):
        raise WorkbenchError(INVALID_TARGET)
    try:
        home = Path.home().resolve()
    except OSError:  # pragma: no cover - defensive
        home = None
    if home is not None and canonical == home:
        # Selecting a folder is not authorization to read the whole user
        # profile; the profile root itself is refused, subfolders are fine.
        raise WorkbenchError(INVALID_TARGET)
    resolved_data_dir = Path(data_dir)
    try:
        resolved_data_dir = resolved_data_dir.resolve()
    except OSError:  # pragma: no cover - defensive
        resolved_data_dir = Path(os.path.abspath(resolved_data_dir))
    if is_within(canonical, resolved_data_dir) or is_within(
        resolved_data_dir, canonical
    ):
        raise WorkbenchError(INVALID_TARGET)
    identity = directory_identity(canonical)
    return FolderCandidate(
        canonical_path=str(canonical),
        directory_identity=identity,
        candidate_id=candidate_id_for(str(canonical), identity),
        suggested_name=canonical.name or str(canonical),
    )


def connection_state(canonical_path: str, identity: str) -> str:
    """Live probe of one recorded binding: never raises, never guesses.

    ``connected`` requires the path to still be a directory and to still
    carry the recorded identity. Everything else -- missing, replaced by
    a file, moved, re-pointed at another folder, unreadable -- is
    ``disconnected``; the same-name folder is never auto-matched.
    """
    try:
        current = Path(canonical_path)
        if is_remote_path(current) or not current.is_absolute():
            return "disconnected"
        if not current.is_dir():
            return "disconnected"
        if directory_identity(current) != identity:
            return "disconnected"
    except (OSError, WorkbenchError, ValueError):
        return "disconnected"
    return "connected"


def assert_contained(child: Path | str, parent: Path | str) -> Path:
    """Reject any subpath that escapes ``parent`` (``..``, link, junction)."""
    try:
        canonical = Path(child).resolve(strict=False)
    except OSError:
        raise WorkbenchError(INVALID_TARGET) from None
    parent_canonical = Path(parent).resolve(strict=False)
    if not is_within(canonical, parent_canonical):
        raise WorkbenchError(INVALID_TARGET)
    return canonical
