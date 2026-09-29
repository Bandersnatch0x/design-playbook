"""The workbench domain owner for projects, bindings, and mutations (R01-R02).

One implementation of "may this directory be a project", "is this
binding still live", and "has this mutation already been applied" lives
here; the HTTP layer and the slash entry point both call these methods
and neither re-derives the rules. Every mutable operation carries a
unique operation ID, the expected entity counter, and a payload whose
digest is recorded with the result, so a retry is either an exact replay
(idempotent, returning the original result) or a typed conflict -- never
a second write.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from .errors import (
    CONFLICT,
    DISCONNECTED,
    INVALID_INPUT,
    INVALID_TARGET,
    UNAUTHORIZED,
    WorkbenchError,
)
from .paths import (
    FolderCandidate,
    connection_state,
    validate_folder_target,
)
from .session import PROJECT_SCOPES
from .store import Store, WorkbenchDataDirectory

CURRENT_PROJECT_SETTING = "currentProjectId"
MAX_NAME_LENGTH = 120
_NAME_CONTROL_PATTERN = re.compile(r"[\x00-\x1f\x7f]")


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    )


@dataclass(frozen=True)
class Operation:
    """MutationEnvelope: unique ID, expected counter, confirmed payload."""

    operation_id: str
    payload: dict
    expected_counter: int | None = None

    @property
    def digest(self) -> str:
        return payload_digest(self.payload)


def payload_digest(payload: dict) -> str:
    """Stable digest of the confirmed payload (reason strings are stable)."""
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def validate_operation(raw: object) -> Operation:
    """Parse one mutation envelope from a request body."""
    if not isinstance(raw, dict):
        raise WorkbenchError(INVALID_INPUT)
    operation_id = raw.get("operationId")
    if not isinstance(operation_id, str) or not _looks_like_token(operation_id):
        raise WorkbenchError(INVALID_INPUT)
    expected = raw.get("expectedCounter", None)
    if expected is not None and (
        isinstance(expected, bool) or not isinstance(expected, int) or expected < 0
    ):
        raise WorkbenchError(INVALID_INPUT)
    payload = raw.get("payload", {})
    if not isinstance(payload, dict):
        raise WorkbenchError(INVALID_INPUT)
    return Operation(operation_id=operation_id, payload=payload, expected_counter=expected)


def _looks_like_token(value: str) -> bool:
    return 8 <= len(value) <= 128 and all(
        character.isalnum() or character in "-_." for character in value
    )


def validate_name(value: object) -> str:
    if not isinstance(value, str):
        raise WorkbenchError(INVALID_INPUT)
    name = value.strip()
    if not name or len(name) > MAX_NAME_LENGTH:
        raise WorkbenchError(INVALID_INPUT)
    if _NAME_CONTROL_PATTERN.search(name):
        raise WorkbenchError(INVALID_INPUT)
    return name


class WorkbenchService:
    """Projects, folder bindings, grants, and the mutation ledger."""

    def __init__(
        self,
        *,
        store: Store,
        data_dir: WorkbenchDataDirectory,
        now_fn: Callable[[], str] | None = None,
    ) -> None:
        self.store = store
        self.data_dir = data_dir
        self._now = now_fn if now_fn is not None else utc_now

    # -- probing -------------------------------------------------------

    def probe_folder(
        self, path: object, *, exclude_project_id: str | None = None
    ) -> FolderCandidate:
        """Probe one maintainer-supplied absolute folder without registering.

        ``exclude_project_id`` lets a rebind probe the project's own
        current directory: a rebind is a new confirmation, so the
        project's own binding must not read as a duplicate target.
        """
        candidate = validate_folder_target(path, data_dir=self.data_dir.root)
        conflict = self.store.binding_conflict(
            canonical_path=candidate.canonical_path,
            directory_identity=candidate.directory_identity,
            exclude_project_id=exclude_project_id,
        )
        if conflict is not None:
            # Same folder, or a different spelling of it (symlink, junction,
            # 8.3 alias, case variant): one project per real directory.
            raise WorkbenchError(INVALID_TARGET)
        return candidate

    def _confirm_candidate(self, path: object, candidate_id: object) -> FolderCandidate:
        candidate = validate_folder_target(path, data_dir=self.data_dir.root)
        if not isinstance(candidate_id, str) or candidate_id != candidate.candidate_id:
            # The confirmation must name exactly the path and identity that
            # were shown; anything else is a rebind the maintainer never saw.
            raise WorkbenchError(INVALID_TARGET)
        return candidate

    # -- mutation discipline -------------------------------------------

    def _replay(
        self, operation: Operation, *, kind: str, entity_id: str | None = None,
        project_id: str | None = None,
    ) -> dict | None:
        """The one mutation-replay gate shared by every service.

        A recorded mutation only replays when the operation id, the payload
        digest, the entity kind and -- for an operation that targets an
        existing entity -- the entity id all match. Reusing an operation id
        against a different target, kind, or payload is a conflict, never a
        replay of some other entity's success.
        """
        recorded = self.store.mutation(operation.operation_id)
        if recorded is None:
            return None
        if (
            recorded["payload_digest"] != operation.digest
            or recorded["entity_kind"] != kind
            or (entity_id is not None and recorded["entity_id"] != entity_id)
            or (project_id is not None and recorded["project_id"] != project_id)
        ):
            raise WorkbenchError(CONFLICT, operation_id=operation.operation_id)
        return {
            "result": json.loads(recorded["result_json"]),
            "counter": recorded["resulting_counter"],
            "replayed": True,
        }

    def _mutate_existing(
        self,
        *,
        kind: str,
        entity_id: str,
        project_id: str | None,
        operation: Operation,
        current_counter: Callable[[], int],
        apply: Callable[[], tuple[dict, int]],
    ) -> dict:
        replayed = self._replay(operation, kind=kind, entity_id=entity_id, project_id=project_id)
        if replayed is not None:
            return replayed
        with self.store.transaction():
            # Re-check inside the transaction: two concurrent requests with
            # the same counter can otherwise both pass the pre-check.
            again = self.store.mutation(operation.operation_id)
            if again is not None:
                raise WorkbenchError(CONFLICT, operation_id=operation.operation_id)
            counter = current_counter()
            if operation.expected_counter is None:
                raise WorkbenchError(INVALID_INPUT, operation_id=operation.operation_id)
            if operation.expected_counter != counter:
                raise WorkbenchError(CONFLICT, operation_id=operation.operation_id)
            result, new_counter = apply()
            self.store.record_mutation(
                operation_id=operation.operation_id,
                entity_kind=kind,
                entity_id=entity_id,
                payload_digest=operation.digest,
                resulting_counter=new_counter,
                result_json=json.dumps(result, separators=(",", ":"), sort_keys=True),
                project_id=project_id,
                now=self._now(),
            )
        return {"result": result, "counter": new_counter, "replayed": False}

    def _mutate_new(
        self,
        *,
        kind: str,
        operation: Operation,
        project_id_fn: Callable[[dict], str],
        apply: Callable[[], dict],
    ) -> dict:
        replayed = self._replay(operation, kind=kind)
        if replayed is not None:
            return replayed
        with self.store.transaction():
            again = self.store.mutation(operation.operation_id)
            if again is not None:
                raise WorkbenchError(CONFLICT, operation_id=operation.operation_id)
            result = apply()
            self.store.record_mutation(
                operation_id=operation.operation_id,
                entity_kind=kind,
                entity_id=project_id_fn(result),
                payload_digest=operation.digest,
                resulting_counter=None,
                result_json=json.dumps(result, separators=(",", ":"), sort_keys=True),
                project_id=project_id_fn(result),
                now=self._now(),
            )
        return {"result": result, "counter": None, "replayed": False}

    # -- project targets ------------------------------------------------

    def project_target(self, project_id: str) -> dict:
        """One live-validated ProjectTarget; disconnected is reported, not hidden."""
        try:
            row = self.store.project(project_id)
        except KeyError:
            raise WorkbenchError(INVALID_TARGET) from None
        binding = self.store.active_binding(project_id)
        if binding is None:  # pragma: no cover - invariant
            raise WorkbenchError(INVALID_TARGET)
        state = connection_state(
            binding["canonical_path"], binding["directory_identity"]
        )
        probed_at = self._now()
        if state != binding["last_known_state"]:
            self.store.touch_binding_state(
                binding_id=binding["binding_id"], state=state, probed_at=probed_at
            )
        return self._target_payload(row, binding, state=state, probed_at=probed_at)

    def _target_payload(
        self, row: dict, binding: dict, *, state: str, probed_at: str
    ) -> dict:
        return {
            "projectId": row["project_id"],
            "name": row["name"],
            "archived": bool(row["archived"]),
            "counter": int(row["counter"]),
            "bindingGeneration": int(binding["generation"]),
            "canonicalPath": binding["canonical_path"],
            "directoryIdentity": binding["directory_identity"],
            "connectionState": state,
            "grantScopes": self.store.grants(row["project_id"]),
            "lastProbedAt": probed_at,
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    def projects_overview(self) -> dict:
        targets = [self.project_target(row["project_id"]) for row in self.store.list_projects()]
        current = self.store.get_setting(CURRENT_PROJECT_SETTING)
        if current is not None and not any(
            target["projectId"] == current for target in targets
        ):
            # A registration removed elsewhere must not leave a dangling
            # "current project" pointer behind.
            self.store.clear_setting(CURRENT_PROJECT_SETTING)
            current = None
        return {"projects": targets, "currentProjectId": current}

    def require_project(self, project_id: str, *, scope: str = "read") -> dict:
        """The one authorization + liveness gate every project operation uses."""
        target = self.project_target(project_id)
        if scope not in target["grantScopes"]:
            raise WorkbenchError(UNAUTHORIZED)
        if target["connectionState"] != "connected":
            raise WorkbenchError(DISCONNECTED)
        return target

    # -- project lifecycle ----------------------------------------------

    def register_project(
        self, *, path: object, candidate_id: object, name: object, operation: Operation
    ) -> dict:
        candidate = self._confirm_candidate(path, candidate_id)
        resolved_name = validate_name(
            candidate.suggested_name if name in (None, "") else name
        )
        now = self._now()

        def apply() -> dict:
            # The duplicate check belongs inside the transaction: a retry of
            # an already-applied registration must replay its recorded
            # result, not re-evaluate the world it already changed.
            conflict = self.store.binding_conflict(
                canonical_path=candidate.canonical_path,
                directory_identity=candidate.directory_identity,
                exclude_project_id=None,
            )
            if conflict is not None:
                raise WorkbenchError(INVALID_TARGET)
            project_id = self.store.create_project_with_binding(
                name=resolved_name,
                canonical_path=candidate.canonical_path,
                directory_identity=candidate.directory_identity,
                now=now,
            )
            return self.project_target(project_id)

        return self._mutate_new(
            kind="project",
            operation=operation,
            project_id_fn=lambda result: result["projectId"],
            apply=apply,
        )

    def rename_project(
        self, project_id: str, *, name: object, operation: Operation
    ) -> dict:
        self._require_exists(project_id)
        resolved_name = validate_name(name)
        now = self._now()

        def apply() -> tuple[dict, int]:
            counter = self.store.rename_project(
                project_id=project_id, name=resolved_name, now=now
            )
            return self.project_target(project_id), counter

        return self._mutate_existing(
            kind="project",
            entity_id=project_id,
            project_id=project_id,
            operation=operation,
            current_counter=lambda: int(self.store.project(project_id)["counter"]),
            apply=apply,
        )

    def _require_exists(self, project_id: str) -> None:
        if not self.store.project_exists(project_id):
            raise WorkbenchError(INVALID_TARGET)

    def set_grants(
        self, project_id: str, *, scopes: object, operation: Operation
    ) -> dict:
        self._require_exists(project_id)
        if not isinstance(scopes, list) or any(
            not isinstance(scope, str) or scope not in PROJECT_SCOPES for scope in scopes
        ):
            raise WorkbenchError(INVALID_INPUT)
        if len(set(scopes)) != len(scopes):
            raise WorkbenchError(INVALID_INPUT)
        if "read" not in scopes:
            raise WorkbenchError(INVALID_INPUT)
        now = self._now()

        def apply() -> tuple[dict, int]:
            self.store.set_grants(project_id=project_id, scopes=sorted(scopes), now=now)
            return self.project_target(project_id), int(
                self.store.project(project_id)["counter"]
            )

        return self._mutate_existing(
            kind="project-grants",
            entity_id=project_id,
            project_id=project_id,
            operation=operation,
            current_counter=lambda: int(self.store.project(project_id)["counter"]),
            apply=apply,
        )

    def rebind_project(
        self, project_id: str, *, path: object, candidate_id: object, operation: Operation
    ) -> dict:
        self._require_exists(project_id)
        candidate = self._confirm_candidate(path, candidate_id)
        now = self._now()

        def apply() -> tuple[dict, int]:
            conflict = self.store.binding_conflict(
                canonical_path=candidate.canonical_path,
                directory_identity=candidate.directory_identity,
                exclude_project_id=project_id,
            )
            if conflict is not None:
                raise WorkbenchError(INVALID_TARGET)
            self.store.rebind_project(
                project_id=project_id,
                canonical_path=candidate.canonical_path,
                directory_identity=candidate.directory_identity,
                now=now,
            )
            return self.project_target(project_id), int(
                self.store.project(project_id)["counter"]
            )

        return self._mutate_existing(
            kind="project-rebind",
            entity_id=project_id,
            project_id=project_id,
            operation=operation,
            current_counter=lambda: int(self.store.project(project_id)["counter"]),
            apply=apply,
        )

    def open_project(self, project_id: str, *, operation: Operation) -> dict:
        self.require_project(project_id, scope="read")

        def apply() -> tuple[dict, int]:
            self.store.set_setting(CURRENT_PROJECT_SETTING, project_id)
            return self.projects_overview(), 0

        return self._mutate_existing(
            kind="setting",
            entity_id=CURRENT_PROJECT_SETTING,
            project_id=project_id,
            operation=operation,
            current_counter=lambda: 0,
            apply=apply,
        )

    def remove_project(self, project_id: str, *, operation: Operation) -> dict:
        """Unregister only: the maintainer's source files are never touched."""
        replayed = self._replay(operation, kind="project-removal", project_id=project_id)
        if replayed is not None:
            # The entity is already gone; the retry still gets its original
            # result instead of a misleading invalid-target.
            return replayed
        self._require_exists(project_id)
        was_current = self.store.get_setting(CURRENT_PROJECT_SETTING) == project_id
        counter_before = int(self.store.project(project_id)["counter"])

        def apply() -> tuple[dict, int]:
            self.store.delete_project(project_id)
            if was_current:
                self.store.clear_setting(CURRENT_PROJECT_SETTING)
            return {"removed": project_id}, counter_before + 1

        outcome = self._mutate_existing(
            kind="project-removal",
            entity_id=project_id,
            project_id=project_id,
            operation=operation,
            current_counter=lambda: int(self.store.project(project_id)["counter"]),
            apply=apply,
        )
        return outcome

    # -- capability issuance -------------------------------------------

    def capability_plan(self, project_id: str, *, scopes: list[str]) -> list[str]:
        """The scopes a slash capability may carry for one project."""
        granted = set(self.store.grants(project_id))
        requested = set(scopes)
        unknown = requested - set(PROJECT_SCOPES)
        if unknown or not requested:
            raise WorkbenchError(UNAUTHORIZED)
        if not requested <= granted:
            # A capability can never exceed the project's own grant.
            raise WorkbenchError(UNAUTHORIZED)
        return sorted(requested)
