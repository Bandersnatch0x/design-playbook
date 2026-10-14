"""Durable Preview record IO: the atomic write primitive and the entry readers.

These are the bytes-on-disk rules for one decision round - what a valid entry is,
how a confirm record is rebuilt and compared, how log.md is rendered and how a
ledger row is shaped. None of them takes a lock; the transaction owns ordering.
"""
from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from design_playbook.mcp.preview.integrity import (
    _MISSING,
    compute_binding_digest,
    confirm_name,
    prototype_name,
)
from design_playbook.mcp.preview.transaction_errors import (
    ConfirmRecordError,
    TransactionConflict,
)

ENTRY_SCHEMA_VERSION = 1

# ponytail: fixed 4x25ms retry covers AV/indexer WinError-5 windows on
# Windows; backoff only if field reports ever exceed ~100ms.
_REPLACE_RETRY_ATTEMPTS = 4
_REPLACE_RETRY_SECONDS = 0.025

def atomic_write(path: Path, content: str) -> None:
    """Flush a same-directory temporary file before atomically replacing path."""
    if path.is_symlink():
        raise ValueError(f"refusing write through symlinked file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        for attempt in range(_REPLACE_RETRY_ATTEMPTS):
            try:
                os.replace(temp_name, path)
                break
            except PermissionError:
                # Windows: a freshly written target (e.g. log.md replaced by a
                # prior writer milliseconds ago) can be briefly held open by
                # AV/indexer scanning, making os.replace fail with WinError 5.
                # The conflict is transient; retry the same temp file instead
                # of surfacing a spurious commit failure.
                if os.name != "nt" or attempt == _REPLACE_RETRY_ATTEMPTS - 1:
                    raise
                time.sleep(_REPLACE_RETRY_SECONDS)
    except BaseException:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise

def json_text(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"

def load_entry(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        entry = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise TransactionConflict(
            f"round decision metadata is unreadable; use next round: {path}",
            retryable=False, round_n=_round_from_path(path), decision_id="",
            artifact=str(path),
        ) from exc
    required = {
        "schema_version", "decision_id", "timestamp", "binding", "outcome"
    }
    round_n = _round_from_path(path)
    binding = entry.get("binding") if isinstance(entry, dict) else None
    outcome = entry.get("outcome") if isinstance(entry, dict) else None
    prototype_mode = entry.get("prototype_mode") if isinstance(entry, dict) else None
    prototype_path = entry.get("prototype_path") if isinstance(entry, dict) else None
    binding_valid = False
    if isinstance(binding, dict):
        try:
            # Rebuild against the same era the record was written in: a
            # missing route_url (pre-live-route record) stays absent from the
            # canonical bytes and from the strict equality check, while an
            # explicit value — including "" — is required to match exactly.
            expected = compute_binding_digest(
                round_n=round_n,
                prototype_html_hash=binding["prototype_html_hash"],
                report_ref=binding["report_ref"], summary=binding["summary"],
                options=binding["options"],
                route_url=binding.get("route_url", _MISSING),
            )
            binding_valid = binding == expected
        except (KeyError, TypeError):
            binding_valid = False
    if (
        not isinstance(entry, dict)
        or entry.get("schema_version") != ENTRY_SCHEMA_VERSION
        or not required.issubset(entry)
        or not isinstance(entry.get("decision_id"), str)
        or not entry["decision_id"]
        or not isinstance(entry.get("timestamp"), str)
        or not binding_valid
        or not isinstance(outcome, dict)
        or not isinstance(outcome.get("selected_options"), list)
        or not isinstance(outcome.get("anchors"), list)
        or not isinstance(outcome.get("feedback"), str)
        or not isinstance(outcome.get("confirmed"), bool)
        or not isinstance(outcome.get("user_confirmed"), bool)
        or not isinstance(outcome.get("floor_pass"), bool)
        or not isinstance(outcome.get("aborted"), bool)
        or prototype_mode not in (None, "html", "path")
        or prototype_mode == "path" and (
            not isinstance(prototype_path, str) or not prototype_path.strip()
        )
    ):
        raise TransactionConflict(
            f"round decision metadata is invalid; use next round: {path}",
            retryable=False, round_n=round_n, decision_id="",
            artifact=str(path),
        )
    return entry

def _round_from_path(path: Path) -> int:
    try:
        return int(path.stem.rsplit("-", 1)[1])
    except (IndexError, ValueError):
        return 0

def _confirm_record(entry: dict[str, Any]) -> dict[str, Any]:
    binding = entry["binding"]
    outcome = entry["outcome"]
    record: dict[str, Any] = {
        "round": binding["round"],
        "report_ref": binding["report_ref"],
        "confirmed": outcome["confirmed"],
        "floor_pass": outcome["floor_pass"],
        "selected_options": outcome["selected_options"],
        "feedback": outcome["feedback"],
        "timestamp": entry["timestamp"],
        "prototype_path": f"preview/{prototype_name(binding['round'])}",
        "prototype_html_hash": binding["prototype_html_hash"],
        "decision_id": entry["decision_id"],
    }
    if outcome.get("floor_failure"):
        record["floor_failure"] = outcome["floor_failure"]
    if outcome.get("criteria_review"):
        record["criteria_review"] = list(outcome["criteria_review"])
    if outcome.get("visual_edits"):
        record["visual_edits"] = dict(outcome["visual_edits"])
    if outcome.get("visual_edits_error"):
        record["visual_edits_error"] = str(outcome["visual_edits_error"])
    if outcome.get("visual_handoff"):
        record["visual_handoff"] = dict(outcome["visual_handoff"])
    return record

def load_confirm_for_entry(
    preview_dir: Path, entry: dict[str, Any], *, allow_legacy: bool = True,
) -> dict[str, Any] | None:
    binding = entry["binding"]
    outcome = entry["outcome"]
    round_n = int(binding["round"])
    path = preview_dir / confirm_name(round_n)
    if not path.is_file():
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConfirmRecordError(f"confirm record unreadable: {path}") from exc
    if not isinstance(record, dict):
        raise ConfirmRecordError(f"confirm record invalid: {path}")
    expected = _confirm_record(entry)
    if "decision_id" not in record:
        if not allow_legacy:
            raise ConfirmRecordError(f"legacy confirm record is invalid: {path}")
        del expected["decision_id"]
    elif not isinstance(record.get("decision_id"), str):
        raise ConfirmRecordError(f"confirm record invalid: {path}")
    elif record["decision_id"] != entry["decision_id"]:
        raise ConfirmRecordError(f"confirm decision mismatch: {path}")
    if not outcome.get("user_confirmed"):
        raise ConfirmRecordError(f"confirm record is unexpected: {path}")
    if record != expected:
        raise ConfirmRecordError(f"confirm record invalid: {path}")
    return record

def render_log(entries: list[dict[str, Any]]) -> str:
    blocks = ["# preview log\n"]
    for entry in sorted(
        entries, key=lambda item: (str(item["timestamp"]), str(item["decision_id"]))
    ):
        binding = entry["binding"]
        outcome = entry["outcome"]
        anchors = list(outcome.get("anchors") or [])
        lines = [
            "",
            f"## round {binding['round']}",
            f"- report_ref: {binding['report_ref']}",
            f"- timestamp: {entry['timestamp']}",
            f"- decision_id: {entry['decision_id']}",
            f"- feedback: {outcome.get('feedback') or ''}",
            f"- selected: {', '.join(outcome.get('selected_options') or [])}",
            f"- aborted: {str(bool(outcome.get('aborted'))).lower()}",
            f"- anchors: {len(anchors)}",
            f"- floor_pass: {str(bool(outcome.get('floor_pass'))).lower()}",
        ]
        if outcome.get("timeout"):
            lines.append("- timeout: true")
        if outcome.get("floor_failure"):
            lines.append(f"- floor_failure: {outcome['floor_failure']}")
        if outcome.get("rejected"):
            lines.append("- rejected: true")
            if outcome.get("rejection"):
                lines.append(f"- rejection: {outcome['rejection']}")
        for index, anchor in enumerate(anchors, 1):
            lines.append(
                f"  - [{index}] {anchor.get('selector') or ''} | "
                f"{anchor.get('label') or ''} | {anchor.get('comment') or ''}"
            )
        blocks.append("\n".join(lines) + "\n")
    return "".join(blocks)

def valid_entries(preview_dir: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in preview_dir.glob("decision-round-*.json"):
        entry = load_entry(path)
        if entry is not None:
            entries.append(entry)
    return entries

def _ledger_record(entry: dict[str, Any]) -> dict[str, Any]:
    """T-086: the run-external registration for one committed round."""
    binding = entry["binding"]
    outcome = entry["outcome"]
    return {
        "round": int(binding["round"]),
        "decision_id": entry["decision_id"],
        "timestamp": entry["timestamp"],
        "confirmed": outcome["confirmed"],
        "floor_pass": outcome["floor_pass"],
        "aborted": outcome["aborted"],
        "binding_digest": binding["digest"],
    }
