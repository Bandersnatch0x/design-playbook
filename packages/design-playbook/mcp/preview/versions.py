"""Local version control for Preview runs: event sourcing + named snapshots.

Compatibility-only lifecycle (ADR-0027). This module is frozen: no new
authoring command, caller, schema, or feature behavior is added here.
Existing read behavior (``state_at``, ``timeline``, ``list_versions``,
``render_versions_log``, ``refresh_version_projection``) and ``fork`` remain
compatible while production transactions depend on ``render_versions_log``
for log projection. Physical removal is targeted for v1.0.0 as project
migration policy, not a SemVer requirement; see
``docs/deprecations/preview-versions.md`` for the removal checklist and the
long-lived owner that must absorb compatibility reading and log projection
before this module can be deleted.

Extends transaction.py's append-only decision entries with:

- named versions (``version-<seq>.json`` — meta-events, append-only)
- ``state_at(round_n)`` replay (read-only, non-destructive)
- ``fork(...)`` deriving an independent linear chain in a new directory
- ``timeline()`` unified view (decisions + versions, timestamp-ordered)

Design: ``assets/vc-data-model.md`` (wayfinder canvas-upgrade ticket 05).

Pure additive: entry schema stays v1; ``validate_run.py`` read-side ignores
unknown fields; G5 invariants (lock / round increment / "use next round")
are untouched.
"""
from __future__ import annotations

import shutil
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from design_playbook.mcp.preview.integrity import decision_name
from design_playbook.mcp.preview.transaction import (
    DirectoryLockError,
    PROJECTION_LOCK_NAME,
    atomic_write,
    directory_lock,
    json_text,
    load_confirm_for_entry,
    load_entry,
    render_log,
    valid_entries,
)
from design_playbook.mcp.preview import compatibility
from design_playbook.mcp.util import now_iso as _now_iso

VERSION_SCHEMA_VERSION = 1
MAX_NAME_LENGTH = 80
MAX_NOTE_LENGTH = 200
VALID_KINDS = {"confirmed", "revised", "custom"}
VERSION_LOCK_NAME = ".versions.lock"


class VersionError(ValueError):
    """Recoverable versioning failure with actionable artifact context."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.details = {"error": "preview_version", "message": message}


class VersionCommittedError(VersionError):
    """A version authority committed before a later operation failed."""

    def __init__(
        self, message: str, *, version_record: dict[str, Any],
        version_record_path: Path, repair_action: str,
    ) -> None:
        super().__init__(message)
        self.committed = True
        self.version_record = dict(version_record)
        self.version_record_path = version_record_path
        self.repair_action = repair_action
        self.details.update({
            "error": "preview_version_committed",
            "committed": True,
            "version_record": dict(version_record),
            "version_record_path": str(version_record_path),
            "repair_action": self.repair_action,
        })


class VersionProjectionError(VersionCommittedError):
    """A version authority committed, but its derived log needs repair."""

    def __init__(
        self, message: str, *, version_record: dict[str, Any],
        version_record_path: Path,
    ) -> None:
        super().__init__(
            message,
            version_record=version_record,
            version_record_path=version_record_path,
            repair_action="refresh_version_projection(preview_dir)",
        )
        self.details["error"] = "preview_version_projection"


def _version_path(preview_dir: Path, seq: int) -> Path:
    return preview_dir / f"version-{seq}.json"


@contextmanager
def _version_lock(preview_dir: Path) -> Iterator[None]:
    """Serialize directory-wide version sequence allocation and projection.

    Reuses transaction's single directory-lock policy (ADR-0024); only the
    lock filename is version-specific.
    """
    try:
        with directory_lock(preview_dir, VERSION_LOCK_NAME):
            yield
    except DirectoryLockError as exc:
        raise VersionError(f"version writer lock failed: {exc}") from exc


def _valid_versions(preview_dir: Path) -> list[dict[str, Any]]:
    try:
        return compatibility.list_versions(preview_dir)
    except compatibility.VersionError as exc:
        raise VersionError(str(exc)) from exc


def _next_seq(preview_dir: Path) -> int:
    seqs = [record["seq"] for record in _valid_versions(preview_dir)]
    return (max(seqs) + 1) if seqs else 1


def create_named_version(
    preview_dir: Path, *, round_n: int, name: str,
    kind: str = "custom", note: str = "",
) -> dict[str, Any]:
    """Write an append-only ``version-<seq>.json`` meta-event for a round.

    Deprecated (ADR-0027): Preview versions are in a compatibility-only
    lifecycle. This authoring entry point is frozen - do not add new callers
    or extend its behavior. It remains for backward-compatible artifact
    creation while the migration to the long-lived owner is pending; see
    ``docs/deprecations/preview-versions.md``.

    The named round must already have a durable decision entry. Versions are
    immutable: a rename is a new version event, never an overwrite.
    """
    name = (name or "").strip()
    if not name:
        raise VersionError("version name must be non-empty")
    if len(name) > MAX_NAME_LENGTH:
        raise VersionError(
            f"version name too long ({len(name)} > {MAX_NAME_LENGTH})")
    if kind not in VALID_KINDS:
        raise VersionError(f"invalid version kind: {kind!r}")
    record: dict[str, Any] | None = None
    path: Path | None = None
    try:
        with _version_lock(preview_dir):
            entry = load_entry(preview_dir / decision_name(round_n))
            if entry is None:
                raise VersionError(f"round {round_n} has no decision entry")
            seq = _next_seq(preview_dir)
            path = _version_path(preview_dir, seq)
            if path.is_file():
                raise VersionError(
                    f"version {seq} already exists (concurrent writer): {path}")
            record = {
                "schema_version": VERSION_SCHEMA_VERSION,
                "seq": seq,
                "version_id": f"v-{uuid.uuid4().hex[:8]}",
                "name": name,
                "kind": kind,
                "round": round_n,
                "decision_id": entry["decision_id"],
                "timestamp": _now_iso(),
            }
            if note:
                record["note"] = (note or "").strip()[:MAX_NOTE_LENGTH]
            atomic_write(path, json_text(record))
            try:
                _refresh_log(preview_dir)
            except Exception as exc:
                raise VersionProjectionError(
                    f"version {record['seq']} committed but its projection "
                    f"needs repair; run refresh_version_projection(preview_dir)",
                    version_record=record,
                    version_record_path=path,
                ) from exc
            return record
    except VersionProjectionError:
        raise
    except VersionError as exc:
        if record is not None and path is not None and path.is_file():
            repair_action = (
                "do not retry create_named_version; inspect version_record_path "
                "and run refresh_version_projection(preview_dir)"
            )
            raise VersionCommittedError(
                f"version {record['seq']} committed before writer finalization "
                "failed; do not retry create_named_version",
                version_record=record,
                version_record_path=path,
                repair_action=repair_action,
            ) from exc
        raise


def render_versions_log(preview_dir: Path) -> str:
    """log.md projection incl. versions section (authority = entry/version files)."""
    try:
        return compatibility.render_versions_log(
            preview_dir,
            render_log(valid_entries(preview_dir)),
        )
    except compatibility.VersionError as exc:
        raise VersionError(str(exc)) from exc


def _refresh_log(preview_dir: Path) -> None:
    try:
        with directory_lock(preview_dir, PROJECTION_LOCK_NAME):
            atomic_write(preview_dir / "log.md", render_versions_log(preview_dir))
    except DirectoryLockError as exc:
        raise VersionError(f"version projection lock failed: {exc}") from exc


def refresh_version_projection(preview_dir: Path) -> Path:
    """Rebuild log.md from durable decision and version authority files."""
    try:
        _refresh_log(preview_dir)
    except VersionError:
        raise
    except OSError as exc:
        raise VersionError(f"version projection refresh failed: {exc}") from exc
    return preview_dir / "log.md"


def state_at(preview_dir: Path, round_n: int) -> dict[str, Any]:
    """Replayable state at round N (read-only, non-destructive).

    Returns the durable decision entry, the snapshot HTML (html mode), the
    confirm record if confirmed, and all named versions at or before N.
    Raises VersionError when N has no decision entry.
    """
    decisions = compatibility.DecisionAccess(
        load_entry=load_entry,
        load_confirm_for_entry=load_confirm_for_entry,
        valid_entries=valid_entries,
    )
    try:
        return compatibility.state_at(preview_dir, round_n, decisions)
    except compatibility.VersionError as exc:
        raise VersionError(str(exc)) from exc


def timeline(preview_dir: Path) -> list[dict[str, Any]]:
    """Unified, timestamp-ordered view: decision events + named versions."""
    decisions = compatibility.DecisionAccess(
        load_entry=load_entry,
        load_confirm_for_entry=load_confirm_for_entry,
        valid_entries=valid_entries,
    )
    try:
        return compatibility.timeline(preview_dir, decisions)
    except compatibility.VersionError as exc:
        raise VersionError(str(exc)) from exc


def list_versions(preview_dir: Path) -> list[dict[str, Any]]:
    """Named versions only, ascending seq."""
    try:
        return compatibility.list_versions(preview_dir)
    except compatibility.VersionError as exc:
        raise VersionError(str(exc)) from exc


def fork(
    source_dir: Path, *, branch: str, from_round: int,
    new_dir: Path, report_ref: str, summary: str,
) -> dict[str, Any]:
    """Derive an independent linear chain from round N of source_dir.

    Deprecated (ADR-0027): Preview versions are in a compatibility-only
    lifecycle. This authoring entry point is frozen - do not add new callers
    or extend its behavior. It remains for backward-compatible chain
    derivation while the migration to the long-lived owner is pending; see
    ``docs/deprecations/preview-versions.md``.

    The new chain lives in ``new_dir`` and re-numbers rounds from 1 (G5
    single-thread invariant is preserved per directory). ``fork.json`` records
    the source. Only html-mode sources (round-N.html present) can fork.
    """
    branch = (branch or "").strip()
    if not branch:
        raise VersionError("branch name must be non-empty")
    src = state_at(source_dir, from_round)
    if src["prototype_html"] is None:
        raise VersionError(
            f"source round {from_round} has no html snapshot in {source_dir} "
            "(path-mode prototype cannot fork without an html payload)")
    record: dict[str, Any] = {
        "schema_version": VERSION_SCHEMA_VERSION,
        "branch": branch,
        "forked_from_round": from_round,
        "forked_from_digest": src["digest"],
        "forked_from_decision_id": src["decision_id"],
        "forked_from_dir": str(source_dir),
        "report_ref": (report_ref or "").strip(),
        "summary": (summary or "").strip(),
        "timestamp": _now_iso(),
    }
    parent = new_dir.parent
    parent.mkdir(parents=True, exist_ok=True)
    lock_name = f".{new_dir.name}.fork.lock"
    staging = parent / f".{new_dir.name}.{uuid.uuid4().hex}.tmp"
    try:
        with directory_lock(parent, lock_name):
            if new_dir.exists() or new_dir.is_symlink():
                raise VersionError(f"fork destination already exists: {new_dir}")
            staging.mkdir(exist_ok=False)
            try:
                atomic_write(staging / "round-1.html", src["prototype_html"])
                atomic_write(staging / "fork.json", json_text(record))
                staging.rename(new_dir)
            except BaseException as exc:
                try:
                    shutil.rmtree(staging)
                except FileNotFoundError:
                    pass
                except OSError as cleanup_exc:
                    if isinstance(exc, Exception):
                        raise VersionError(
                            f"fork initialization failed and cleanup failed: "
                            f"{staging}: {cleanup_exc}"
                        ) from exc
                    raise
                if not isinstance(exc, Exception):
                    raise
                raise VersionError(f"fork initialization failed: {new_dir}") from exc
    except DirectoryLockError as exc:
        raise VersionError(f"fork destination lock failed: {new_dir}: {exc}") from exc
    start = new_dir / "round-1.html"
    return {"fork": record, "start_prototype": str(start)}
