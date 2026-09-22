"""Diagnostic export transaction (ADR-0044, contract spec §4).

The one run-tree-writing capability of the Run Console: a two-phase
transaction that projects the currently served, validated Snapshot v1
document into the export pair (``diagnostic_export``), previews it without
writing anything, and — only after the participant-reviewed write request
re-binds ``expectedSourceSetHash`` and ``previewHash`` — commits exactly one
JSON/Markdown pair under ``<run_root>/trial-export/`` through the shared
containment authority, then performs one full snapshot rebuild.

Discipline this module owns:

* every rejection before commit is zero-effect: no file, no state change;
* the commit is staged (both files written to temporary names inside the
  boundary, then renamed into place); a failed second rename rolls the
  first back, so no partial pair survives (S36);
* bindings are re-derived from the current snapshot under the session's
  transaction lock — a rebuilt snapshot between preview and write is the
  typed mismatch, never a silent stale write (S36);
* absolute paths never appear in any response; written paths are
  run-root-relative.

This module opens no socket and spawns no process; its only effect is the
bounded file pair below ``trial-export/`` and the rebuild.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from . import diagnostic_export
from .session import RunConsoleSession, RunConsoleSessionError

# Re-exported error vocabulary (request_security is the fixed-code owner).
from .request_security import (  # noqa: F401
    EXPORT_PREVIEW_MISMATCH,
    EXPORT_WRITE_FAILED,
)
from design_playbook.mcp.evidence.containment import trial_export_write_target

_JSON_SUFFIX = ".json"
_MARKDOWN_SUFFIX = ".md"
_NAME_HASH_CHARS = 12


class ExportTransactionError(ValueError):
    """A typed transaction failure (binding mismatch or commit failure)."""

    def __init__(self, code: str, message: str | None = None) -> None:
        super().__init__(
            message
            if message is not None
            else (
                "The export preview no longer matches the current snapshot."
                if code == EXPORT_PREVIEW_MISMATCH
                else "The export transaction failed atomically."
            )
        )
        self.code = code


@dataclass(frozen=True)
class ExportPreview:
    """The exact candidate pair plus the bindings a write must re-present."""

    preview_hash: str
    source_set_hash: str
    json_document: dict
    markdown: str


@dataclass(frozen=True)
class ExportCommit:
    """The written pair (run-root-relative names) and the rebuilt document."""

    written: tuple[str, ...]
    snapshot: dict


def _candidate(
    session: RunConsoleSession, participant_ref: str | None
) -> tuple[dict, str, str]:
    """Project the current snapshot to (document, preview hash, source hash)."""
    document = session.build_snapshot()
    candidate = diagnostic_export.build_export_document(
        document,
        participant_ref=participant_ref,
    )
    return candidate, diagnostic_export.preview_hash(candidate), document[
        "sources"
    ]["sourceSetHash"]


def perform_preview(
    session: RunConsoleSession, participant_ref: str | None
) -> ExportPreview:
    """Build the exact candidate pair; write nothing anywhere."""
    if session.closed:
        raise RunConsoleSessionError("SESSION_CLOSED")
    with session.transaction_lock():
        candidate, digest, source_set_hash = _candidate(session, participant_ref)
        return ExportPreview(
            preview_hash=digest,
            source_set_hash=source_set_hash,
            json_document=candidate,
            markdown=diagnostic_export.render_markdown(candidate),
        )


def _pair_names(preview_hash_hex: str) -> tuple[str, str]:
    stem = "export-" + preview_hash_hex[:_NAME_HASH_CHARS]
    return stem + _JSON_SUFFIX, stem + _MARKDOWN_SUFFIX


def perform_write(
    session: RunConsoleSession,
    *,
    expected_source_set_hash: str,
    preview_hash_hex: str,
    participant_ref: str | None,
) -> ExportCommit:
    """Re-bind, commit the reviewed pair, and rebuild the snapshot.

    Every mismatch is the typed ``EXPORT_PREVIEW_MISMATCH`` with zero
    filesystem effect; a commit failure is the typed
    ``EXPORT_WRITE_FAILED`` with no partial pair left behind.
    """
    if session.closed:
        raise RunConsoleSessionError("SESSION_CLOSED")
    with session.transaction_lock():
        candidate, digest, source_set_hash = _candidate(session, participant_ref)
        if source_set_hash != expected_source_set_hash:
            raise ExportTransactionError(EXPORT_PREVIEW_MISMATCH)
        if digest != preview_hash_hex:
            raise ExportTransactionError(EXPORT_PREVIEW_MISMATCH)
        json_name, markdown_name = _pair_names(digest)
        json_result = trial_export_write_target(json_name, session.run_root)
        markdown_result = trial_export_write_target(markdown_name, session.run_root)
        if not json_result.ok or not markdown_result.ok:
            raise ExportTransactionError(
                EXPORT_WRITE_FAILED, "the export target is outside the boundary"
            )
        assert json_result.path is not None and markdown_result.path is not None
        markdown = diagnostic_export.render_markdown(candidate)
        json_bytes = diagnostic_export.canonical_json_bytes(candidate)
        markdown_bytes = markdown.encode("utf-8")
        # Content-addressed names (contract spec §4.3): an existing target
        # fails closed. In practice the pair itself enters the next
        # snapshot's source set (run-facts / run-status read the run
        # tree), so a repeat write rebinds to a new hash and a new name —
        # repeated exports are ordinary pairs, never overwrites. An
        # existing name can only mean a partial pair from an interrupted
        # transaction or a hash collision; both fail rather than guess.
        if json_result.path.exists() or markdown_result.path.exists():
            raise ExportTransactionError(
                EXPORT_WRITE_FAILED, "the export target already exists"
            )
        subtree = json_result.path.parent
        staged: list[tuple] = [
            (json_result.path, json_bytes),
            (markdown_result.path, markdown_bytes),
        ]
        temp_paths: list = []
        try:
            try:
                subtree.mkdir(parents=True, exist_ok=True)
            except OSError:
                raise ExportTransactionError(EXPORT_WRITE_FAILED) from None
            for target, _payload in staged:
                temp = target.with_name(target.name + ".staged")
                if temp.exists():
                    raise ExportTransactionError(EXPORT_WRITE_FAILED)
                # A temp is appended to the cleanup list only after it is
                # known to be this transaction's own: a rejected attempt
                # must never delete a file it did not create.
                temp_paths.append(temp)
            try:
                for temp, (_, payload) in zip(temp_paths, staged):
                    temp.write_bytes(payload)
            except OSError:
                # A staging failure is the same atomic transaction failure:
                # no partial pair, no stray temp, typed 500 (spec §4.3).
                raise ExportTransactionError(EXPORT_WRITE_FAILED) from None
            placed = 0
            try:
                for temp, (target, _payload) in zip(temp_paths, staged):
                    os.replace(temp, target)
                    placed += 1
            except OSError:
                # Roll back any placed member: no partial pair survives (S36).
                for target, _payload in staged[:placed]:
                    try:
                        target.unlink()
                    except OSError:  # pragma: no cover - defensive
                        pass
                raise ExportTransactionError(EXPORT_WRITE_FAILED) from None
        except ExportTransactionError:
            for temp in temp_paths:
                try:
                    temp.unlink()
                except OSError:  # pragma: no cover - defensive
                    pass
            raise
        written = tuple(
            f"trial-export/{path.name}" for path, _ in staged
        )
        rebuilt = session.rebuild_snapshot()
        return ExportCommit(written=written, snapshot=rebuilt)
