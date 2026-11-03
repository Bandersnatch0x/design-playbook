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

import re
from datetime import datetime, timezone
from typing import Callable

from .errors import (
    CONFLICT,
    DISCONNECTED,
    INVALID_INPUT,
    INVALID_TARGET,
    RECOVERY_REQUIRED,
    UNAUTHORIZED,
    WorkbenchError,
)
# The mutation envelope and its gate are re-exported because every domain
# module imports them from this module; the gate itself lives in mutation.py.
from .mutation import (  # noqa: F401
    MutationGate,
    Operation,
    payload_digest,
    validate_operation,
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
        self.mutations = MutationGate(store, self._now)

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
    #
    # The gate itself lives in mutation.py. This replay forward exists for
    # the writes whose prologue cannot wait for the gate: a journaled
    # filesystem write whose progress must survive a failure, a backup
    # archive, an import closure, and the lease-checked agent writes. Do not
    # add callers that could use the gate's own replay.

    def _replay(
        self, operation: Operation, *, kind: str, entity_id: str | None = None,
        project_id: str | None = None,
    ) -> dict | None:
        return self.mutations.replay(
            operation, kind=kind, entity_id=entity_id, project_id=project_id
        )

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
        return {
            "projects": targets,
            "currentProjectId": current,
            # R13: an unregistered project keeps its data until the maintainer
            # explicitly deletes it, so it stays visible as a deletion target
            # rather than disappearing while its records still exist.
            "removedProjects": [
                {
                    "projectId": row["project_id"],
                    "name": row["name"],
                    "removedAt": row["updated_at"],
                }
                for row in self.store.list_removed_projects()
            ],
        }

    def require_project(
        self,
        project_id: str,
        *,
        scope: str = "read",
        allow_incomplete: bool = False,
    ) -> dict:
        """The one authorization + liveness gate every project operation uses.

        A write scope also refuses while an apply journal for this project is
        unfinished: R06 says a half-applied proposal blocks every other write
        until the maintainer resolves it, not only the next proposal. The
        recovery path passes ``allow_incomplete`` because it is the way out.
        """
        target = self.project_target(project_id)
        if scope not in target["grantScopes"]:
            raise WorkbenchError(UNAUTHORIZED)
        if target["connectionState"] != "connected":
            raise WorkbenchError(DISCONNECTED)
        if scope == "write" and not allow_incomplete:
            if self.store.incomplete_journal(project_id) is not None:
                raise WorkbenchError(RECOVERY_REQUIRED)
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

        def apply() -> tuple[dict, int | None]:
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
            return self.project_target(project_id), None

        return self.mutations.create(
            operation,
            kind="project",
            entity_of=lambda result: result["projectId"],
            project_of=lambda result: result["projectId"],
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

        return self.mutations.existing(
            operation,
            kind="project",
            entity_id=project_id,
            project_id=project_id,
            load_row=lambda: self.store.project(project_id),
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

        return self.mutations.existing(
            operation,
            kind="project-grants",
            entity_id=project_id,
            project_id=project_id,
            load_row=lambda: self.store.project(project_id),
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

        return self.mutations.existing(
            operation,
            kind="project-rebind",
            entity_id=project_id,
            project_id=project_id,
            load_row=lambda: self.store.project(project_id),
            apply=apply,
        )

    def open_project(self, project_id: str, *, operation: Operation) -> dict:
        self.require_project(project_id, scope="read")

        def apply() -> tuple[dict, int]:
            self.store.set_setting(CURRENT_PROJECT_SETTING, project_id)
            return self.projects_overview(), 0

        return self.mutations.existing(
            operation,
            kind="setting",
            entity_id=CURRENT_PROJECT_SETTING,
            project_id=project_id,
            # The setting has no counter of its own: its write is conditional on
            # the project still existing, which require_project already checked.
            load_row=lambda: {"counter": 0},
            apply=apply,
        )

    def remove_project(self, project_id: str, *, operation: Operation) -> dict:
        """Unregister only: the maintainer's source files and data are untouched.

        R13 splits this from deleting the project's workbench data. The row
        and everything under it stay; only the registration (binding) and the
        authorization (grants) go away, so the data is still there for a
        separate, explicit deletion.
        """
        replayed = self.mutations.replay(
            operation, kind="project-removal", project_id=project_id
        )
        if replayed is not None:
            # The entity is already unregistered; the retry still gets its
            # original result instead of a misleading invalid-target.
            return replayed
        self._require_exists(project_id)
        was_current = self.store.get_setting(CURRENT_PROJECT_SETTING) == project_id
        counter_before = int(self.store.project(project_id)["counter"])

        def apply() -> tuple[dict, int]:
            self.store.unregister_project(project_id=project_id, now=self._now())
            if was_current:
                self.store.clear_setting(CURRENT_PROJECT_SETTING)
            return {"removed": project_id}, counter_before + 1

        return self.mutations.existing(
            operation,
            kind="project-removal",
            entity_id=project_id,
            project_id=project_id,
            load_row=lambda: self.store.project(project_id),
            apply=apply,
        )

    def delete_project_data(self, project_id: str, *, operation: Operation) -> dict:
        """Delete this project's workbench data, explicitly and irrevocably.

        Only an unregistered project can be deleted, so one action never
        silently performs the other. The source folder is never touched.
        """
        def apply() -> tuple[dict, int | None]:
            if self.store.project_exists(project_id):
                raise WorkbenchError(CONFLICT, detail="unregister the project first")
            if self.store.removed_project(project_id) is None:
                raise WorkbenchError(INVALID_TARGET)
            self.store.delete_project_data(project_id)
            return {"projectId": project_id, "deleted": True}, None

        return self.mutations.create(
            operation,
            kind="project-data-deletion",
            entity_of=lambda result: result["projectId"],
            project_of=lambda result: None,
            apply=apply,
        )

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
