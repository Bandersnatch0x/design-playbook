"""Read and project frozen Preview version artifacts (ADR-0027).

This module owns compatibility behavior for historical ``version-*.json``
records. It does not author version records. Durable decision validation stays
in ``transaction.py`` and is supplied through ``DecisionAccess`` so dependency
direction remains transaction/versions -> compatibility.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from design_playbook.mcp.preview.integrity import prototype_html_digest

VERSION_SCHEMA_VERSION = 1
VALID_KINDS = frozenset({"confirmed", "revised", "custom"})


class VersionError(ValueError):
    """Recoverable compatibility failure with actionable artifact context."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.details = {"error": "preview_version", "message": message}


@dataclass(frozen=True)
class DecisionAccess:
    """Read-only access to durable decision authority in transaction.py."""

    load_entry: Callable[[Path], dict[str, Any] | None]
    load_confirm_for_entry: Callable[..., dict[str, Any] | None]
    valid_entries: Callable[[Path], list[dict[str, Any]]]


def load_version(path: Path) -> dict[str, Any] | None:
    """Read one frozen version record for compatibility projections."""
    if not path.is_file():
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise VersionError(f"version record unreadable: {path}") from exc
    required = {
        "schema_version", "seq", "version_id", "name", "kind", "round",
        "decision_id", "timestamp",
    }
    if (
        not isinstance(record, dict)
        or record.get("schema_version") != VERSION_SCHEMA_VERSION
        or not required.issubset(record)
        or not isinstance(record.get("seq"), int)
        or not isinstance(record.get("name"), str)
        or not record["name"].strip()
        or record.get("kind") not in VALID_KINDS
        or not isinstance(record.get("round"), int)
        or not isinstance(record.get("decision_id"), str)
        or not isinstance(record.get("timestamp"), str)
    ):
        raise VersionError(f"version record invalid: {path}")
    return record


def list_versions(preview_dir: Path) -> list[dict[str, Any]]:
    """Read valid named versions in ascending sequence order."""
    records: list[dict[str, Any]] = []
    for path in sorted(preview_dir.glob("version-*.json")):
        record = load_version(path)
        if record is not None:
            records.append(record)
    return sorted(records, key=lambda record: record["seq"])


def render_versions_log(preview_dir: Path, decision_log: str) -> str:
    """Append the frozen versions section to a durable decision projection."""
    versions = list_versions(preview_dir)
    if not versions:
        return decision_log
    lines = ["", "## versions"]
    for version in versions:
        lines.append(
            f"- [{version['seq']}] {version['name']} | "
            f"round {version['round']} | {version['kind']} | "
            f"{version['timestamp']}"
        )
    return decision_log + "\n".join(lines)


def state_at(
    preview_dir: Path,
    round_n: int,
    decisions: DecisionAccess,
) -> dict[str, Any]:
    """Read the compatible Preview state at round N."""
    entry = decisions.load_entry(preview_dir / f"decision-round-{round_n}.json")
    if entry is None:
        raise VersionError(f"round {round_n} has no decision entry")

    prototype = preview_dir / f"round-{round_n}.html"
    prototype_html = None
    prototype_path = None
    prototype_mode = entry.get("prototype_mode")
    if prototype_mode is None:
        prototype_mode = "html" if prototype.is_file() else "path"
    if prototype_mode == "html":
        if not prototype.is_file():
            raise VersionError(f"prototype snapshot missing: {prototype}")
        try:
            prototype_bytes = prototype.read_bytes()
            prototype_html = prototype_bytes.decode("utf-8")
            prototype_html = prototype_html.replace("\r\n", "\n").replace("\r", "\n")
        except (OSError, UnicodeError) as exc:
            raise VersionError(f"prototype snapshot unreadable: {prototype}") from exc
        expected_hash = str(entry["binding"].get("prototype_html_hash") or "")
        if prototype_html_digest(prototype_bytes) != expected_hash:
            raise VersionError(f"prototype digest mismatch: {prototype}")
        prototype_path = str(prototype)
    elif prototype_mode == "path":
        stored_path = entry.get("prototype_path")
        if isinstance(stored_path, str) and stored_path.strip():
            prototype_path = stored_path
    else:
        raise VersionError(
            f"invalid prototype mode for round {round_n}: {prototype_mode!r}"
        )

    try:
        confirm = decisions.load_confirm_for_entry(preview_dir, entry)
    except ValueError as exc:
        raise VersionError(str(exc)) from exc
    versions = [v for v in list_versions(preview_dir) if v["round"] <= round_n]
    return {
        "round": round_n,
        "decision_id": entry["decision_id"],
        "prototype_html": prototype_html,
        "prototype_path": prototype_path,
        "binding": entry["binding"],
        "outcome": entry["outcome"],
        "confirm": confirm,
        "versions": versions,
        "digest": entry["binding"]["digest"],
    }


def timeline(preview_dir: Path, decisions: DecisionAccess) -> list[dict[str, Any]]:
    """Merge durable decision events and compatible version events."""
    items: list[dict[str, Any]] = []
    for entry in decisions.valid_entries(preview_dir):
        item = dict(entry)
        item["event_type"] = "decision"
        items.append(item)
    for record in list_versions(preview_dir):
        item = dict(record)
        item["event_type"] = "version"
        items.append(item)
    return sorted(items, key=lambda event: (str(event["timestamp"]), event.get("seq", 0)))
