"""Orchestrator capture-call snapshot: original call fields, no session bytes."""
from __future__ import annotations

from typing import Any

from design_playbook.mcp.evidence.path_syntax import trimmed_relpath

_CALL_KEYS = ("url", "type", "state", "actions", "artifact_path", "storage_state")


def capture_call_snapshot(request: dict[str, Any]) -> dict[str, Any]:
    """Fields needed to re-run a capture.

    ``storage_state`` is the run-root-relative path when present. File
    contents, cookies, and tokens are never copied.
    """
    snapshot: dict[str, Any] = {}
    for key in _CALL_KEYS:
        if key not in request:
            continue
        value = request[key]
        if key == "storage_state":
            if not isinstance(value, str) or not value.strip():
                continue
            snapshot[key] = trimmed_relpath(value)
            continue
        snapshot[key] = value
    return snapshot
