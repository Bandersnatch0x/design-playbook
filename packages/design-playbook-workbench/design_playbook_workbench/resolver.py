"""The one project resolver shared by the Web UI and the slash entry points (R02).

Both callers must arrive at the same ``ProjectTarget`` for the same
inputs, so resolution lives here: an explicit absolute directory or an
explicit project ID is matched against the *registered* bindings, and
nothing else is ever used as a target. There is no home-directory,
install-directory, current-working-directory, or last-used fallback, and
an unregistered directory is refused rather than silently registered --
otherwise a slash command could create a second, competing project
identity for the same folder.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from .errors import (
    DISCONNECTED,
    INVALID_TARGET,
    OWNER_UNAVAILABLE,
    WorkbenchError,
)
from .paths import canonical_directory, directory_identity, is_remote_path

PROJECT_PREFIX = "project"

TaskLookup = Callable[[str], "dict | None"]


def _normalized(value: str) -> str:
    return value.replace("\\", "/").rstrip("/").lower()


def _match_by_directory(service, raw: object) -> str:
    """Find the registered project whose current binding is this directory.

    The comparison is by canonical path first, then by directory identity,
    and finally by normalized recorded path: a folder that was moved still
    resolves to *its* project (which then reports disconnected) instead of
    matching a same-named folder somewhere else.
    """
    if not isinstance(raw, str) or not raw.strip() or is_remote_path(raw):
        raise WorkbenchError(INVALID_TARGET)
    if not Path(raw).is_absolute():
        raise WorkbenchError(INVALID_TARGET)
    try:
        canonical = str(canonical_directory(raw))
        identity = directory_identity(canonical)
    except WorkbenchError:
        canonical = None
        identity = None
    normalized = _normalized(raw)
    for row in service.store.list_projects():
        binding = service.store.active_binding(row["project_id"])
        if binding is None:  # pragma: no cover - invariant
            continue
        if canonical is not None and binding["canonical_path"] == canonical:
            return row["project_id"]
        if identity is not None and binding["directory_identity"] == identity:
            return row["project_id"]
        if _normalized(binding["canonical_path"]) == normalized:
            return row["project_id"]
    raise WorkbenchError(INVALID_TARGET)


def resolve(
    service,
    *,
    project: object = None,
    project_id: object = None,
    request_id: object = None,
    task_lookup: TaskLookup | None = None,
) -> dict:
    """Resolve one explicit target, refusing everything implicit.

    Exactly one of ``project`` (absolute directory) or ``project_id`` must
    be supplied. The project must be registered and currently connected;
    a supplied request ID must match a live task bound to that project.
    """
    has_directory = project not in (None, "")
    has_id = project_id not in (None, "")
    if has_directory == has_id:
        # Missing target and ambiguous target are the same refusal: the
        # caller must state which project it means.
        raise WorkbenchError(INVALID_TARGET)
    if has_id:
        if not isinstance(project_id, str) or not project_id.strip():
            raise WorkbenchError(INVALID_TARGET)
        resolved_id = project_id
        if not service.store.project_exists(resolved_id):
            raise WorkbenchError(INVALID_TARGET)
    else:
        resolved_id = _match_by_directory(service, project)

    target = service.project_target(resolved_id)
    if target["archived"]:
        raise WorkbenchError(INVALID_TARGET)
    if target["connectionState"] != "connected":
        # A moved, deleted, or permission-revoked folder is disconnected:
        # commands stop instead of writing somewhere unexpected.
        raise WorkbenchError(DISCONNECTED)

    payload: dict = {
        "project": target,
        "requestId": None,
        "taskState": None,
    }
    if request_id in (None, ""):
        return payload
    if not isinstance(request_id, str) or not request_id.strip():
        raise WorkbenchError(INVALID_TARGET)
    if task_lookup is None:
        # Without a task registry the request cannot be bound to this
        # service, so the honest answer is that the owner is unavailable
        # rather than a made-up binding.
        raise WorkbenchError(OWNER_UNAVAILABLE)
    task = task_lookup(request_id)
    if task is None:
        raise WorkbenchError(INVALID_TARGET)
    if task.get("project_id") != resolved_id:
        # A request belongs to exactly one project: a mismatched pair is a
        # mis-binding, not a hint to try another project.
        raise WorkbenchError(INVALID_TARGET)
    binding = service.store.active_binding(resolved_id)
    if binding is None or int(task.get("binding_generation", -1)) != int(
        binding["generation"]
    ):
        raise WorkbenchError(INVALID_TARGET)
    payload["requestId"] = request_id
    payload["taskState"] = task.get("state")
    return payload
