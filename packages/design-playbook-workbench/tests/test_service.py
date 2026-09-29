#!/usr/bin/env python3
"""A02/A04 (service half): project lifecycle and mutation discipline.

Drives the domain owner directly: registration defaults, duplicate and
alias refusal, idempotent replay versus conflict, counter staleness,
grants, rebind identity change, and removal that never touches the
maintainer's files.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from design_playbook_workbench.errors import (
    CONFLICT,
    DISCONNECTED,
    INVALID_INPUT,
    INVALID_TARGET,
    UNAUTHORIZED,
    WorkbenchError,
)
from design_playbook_workbench.service import (
    Operation,
    WorkbenchService,
    payload_digest,
    validate_name,
    validate_operation,
)
from design_playbook_workbench.store import Store, WorkbenchDataDirectory

from tests.harness import make_directory_link


class ServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name).resolve()
        self.data_dir = WorkbenchDataDirectory(self.base / "data").ensure()
        self.store = Store(self.data_dir.database_path)
        self.service = WorkbenchService(store=self.store, data_dir=self.data_dir)
        self.workspace = self.base / "workspace"
        self.workspace.mkdir()
        self._operations = 0

    def tearDown(self) -> None:
        self.store.close()
        self._tmp.cleanup()

    def operation(self, payload: dict, *, expected: int | None = None, operation_id: str | None = None):
        if operation_id is None:
            self._operations += 1
            operation_id = f"op_test_{self._operations:08d}"
        return Operation(
            operation_id=operation_id, payload=payload, expected_counter=expected
        )

    def directory(self, name: str) -> Path:
        path = self.workspace / name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def register(self, name: str = "alpha", *, project_name: str | None = None):
        path = self.directory(name)
        candidate = self.service.probe_folder(path)
        outcome = self.service.register_project(
            path=candidate.canonical_path,
            candidate_id=candidate.candidate_id,
            name=project_name,
            operation=self.operation(
                {
                    "action": "register-project",
                    "path": candidate.canonical_path,
                    "candidateId": candidate.candidate_id,
                }
            ),
        )
        return outcome["result"], candidate


class RegistrationTest(ServiceTestCase):
    def test_registration_is_read_only_and_keeps_path_and_identity(self) -> None:
        target, candidate = self.register(project_name="Alpha")
        self.assertEqual(target["name"], "Alpha")
        self.assertEqual(target["canonicalPath"], candidate.canonical_path)
        self.assertEqual(target["directoryIdentity"], candidate.directory_identity)
        self.assertEqual(target["grantScopes"], ["read"])
        self.assertEqual(target["connectionState"], "connected")
        self.assertEqual(target["counter"], 0)
        self.assertEqual(target["bindingGeneration"], 1)

    def test_default_name_comes_from_the_directory(self) -> None:
        target, _ = self.register("beta", project_name=None)
        self.assertEqual(target["name"], "beta")

    def test_same_canonical_path_cannot_be_registered_twice(self) -> None:
        target, candidate = self.register("alpha")
        with self.assertRaises(WorkbenchError) as caught:
            self.service.register_project(
                path=candidate.canonical_path,
                candidate_id=candidate.candidate_id,
                name=None,
                operation=self.operation({"action": "register-project"}),
            )
        self.assertEqual(caught.exception.code, INVALID_TARGET)

    def test_alias_of_a_registered_folder_is_refused(self) -> None:
        target, candidate = self.register("alpha")
        link = self.workspace / "alpha-alias"
        if not make_directory_link(link, Path(candidate.canonical_path)):
            self.skipTest("directory links are unavailable on this host")
        with self.assertRaises(WorkbenchError) as caught:
            self.service.probe_folder(link)
        self.assertEqual(caught.exception.code, INVALID_TARGET)

    def test_confirmation_must_name_the_probed_candidate(self) -> None:
        path = self.directory("gamma")
        candidate = self.service.probe_folder(path)
        for candidate_id in (None, "", "cand_" + "0" * 32, candidate.candidate_id + "x"):
            with self.subTest(candidate_id=candidate_id):
                with self.assertRaises(WorkbenchError) as caught:
                    self.service.register_project(
                        path=candidate.canonical_path,
                        candidate_id=candidate_id,
                        name=None,
                        operation=self.operation({"action": "register-project"}),
                    )
                self.assertEqual(caught.exception.code, INVALID_TARGET)

    def test_replay_of_a_registration_returns_the_first_result(self) -> None:
        path = self.directory("delta")
        candidate = self.service.probe_folder(path)
        operation = self.operation(
            {"action": "register-project", "path": candidate.canonical_path},
            operation_id="op_register_replay_1",
        )
        first = self.service.register_project(
            path=candidate.canonical_path,
            candidate_id=candidate.candidate_id,
            name="Delta",
            operation=operation,
        )
        second = self.service.register_project(
            path=candidate.canonical_path,
            candidate_id=candidate.candidate_id,
            name="Delta",
            operation=operation,
        )
        self.assertFalse(first["replayed"])
        self.assertTrue(second["replayed"])
        self.assertEqual(first["result"], second["result"])
        self.assertEqual(len(self.store.list_projects()), 1)

    def test_names_are_validated(self) -> None:
        for value in ("", "   ", None, 5, "x" * 200, "bad\x00name", "line\nbreak"):
            with self.subTest(value=value):
                with self.assertRaises(WorkbenchError) as caught:
                    validate_name(value)
                self.assertEqual(caught.exception.code, INVALID_INPUT)
        self.assertEqual(validate_name("  Alpha  "), "Alpha")


class MutationDisciplineTest(ServiceTestCase):
    def test_stale_counter_is_a_conflict(self) -> None:
        target, _ = self.register("alpha")
        self.service.rename_project(
            target["projectId"],
            name="Renamed",
            operation=self.operation({"name": "Renamed"}, expected=0),
        )
        with self.assertRaises(WorkbenchError) as caught:
            self.service.rename_project(
                target["projectId"],
                name="Again",
                operation=self.operation({"name": "Again"}, expected=0),
            )
        self.assertEqual(caught.exception.code, CONFLICT)

    def test_missing_counter_is_invalid_input(self) -> None:
        target, _ = self.register("alpha")
        with self.assertRaises(WorkbenchError) as caught:
            self.service.rename_project(
                target["projectId"],
                name="Renamed",
                operation=self.operation({"name": "Renamed"}),
            )
        self.assertEqual(caught.exception.code, INVALID_INPUT)

    def test_same_operation_id_with_a_different_payload_is_a_conflict(self) -> None:
        target, _ = self.register("alpha")
        project_id = target["projectId"]
        self.service.rename_project(
            project_id,
            name="First",
            operation=self.operation(
                {"name": "First"}, expected=0, operation_id="op_sameid_0001"
            ),
        )
        with self.assertRaises(WorkbenchError) as caught:
            self.service.rename_project(
                project_id,
                name="Second",
                operation=self.operation(
                    {"name": "Second"}, expected=1, operation_id="op_sameid_0001"
                ),
            )
        self.assertEqual(caught.exception.code, CONFLICT)

    def test_exact_replay_returns_the_recorded_result_without_writing_again(self) -> None:
        target, _ = self.register("alpha")
        project_id = target["projectId"]
        operation = self.operation(
            {"name": "First"}, expected=0, operation_id="op_replay_0001"
        )
        first = self.service.rename_project(project_id, name="First", operation=operation)
        again = self.service.rename_project(project_id, name="First", operation=operation)
        self.assertTrue(again["replayed"])
        self.assertEqual(first["result"], again["result"])
        self.assertEqual(self.store.project(project_id)["counter"], 1)

    def test_payload_digest_is_order_independent_but_content_sensitive(self) -> None:
        self.assertEqual(
            payload_digest({"a": 1, "b": 2}), payload_digest({"b": 2, "a": 1})
        )
        self.assertNotEqual(payload_digest({"a": 1}), payload_digest({"a": 2}))
        self.assertTrue(payload_digest({}).startswith("sha256:"))

    def test_operation_envelope_validation(self) -> None:
        valid = validate_operation({"operationId": "op_valid_0001", "payload": {}})
        self.assertEqual(valid.operation_id, "op_valid_0001")
        self.assertIsNone(valid.expected_counter)
        with_counter = validate_operation(
            {"operationId": "op_valid_0002", "payload": {"a": 1}, "expectedCounter": 3}
        )
        self.assertEqual(with_counter.expected_counter, 3)
        for raw in (
            None,
            [],
            {},
            {"operationId": "short", "payload": {}},
            {"operationId": "op_valid_0001", "payload": []},
            {"operationId": "op_valid_0001", "payload": {}, "expectedCounter": -1},
            {"operationId": "op_valid_0001", "payload": {}, "expectedCounter": "1"},
            {"operationId": "op_valid_0001", "payload": {}, "expectedCounter": True},
            {"operationId": "op with spaces", "payload": {}},
        ):
            with self.subTest(raw=raw):
                with self.assertRaises(WorkbenchError) as caught:
                    validate_operation(raw)
                self.assertEqual(caught.exception.code, INVALID_INPUT)


class GrantsAndCapabilityTest(ServiceTestCase):
    def test_grants_replace_atomically_and_require_read(self) -> None:
        target, _ = self.register("alpha")
        project_id = target["projectId"]
        updated = self.service.set_grants(
            project_id,
            scopes=["read", "write"],
            operation=self.operation({"scopes": ["read", "write"]}, expected=0),
        )["result"]
        self.assertEqual(updated["grantScopes"], ["read", "write"])
        for scopes in ([], ["write"], ["read", "read"], ["read", "bogus"], "read"):
            with self.subTest(scopes=scopes):
                with self.assertRaises(WorkbenchError) as caught:
                    self.service.set_grants(
                        project_id,
                        scopes=scopes,
                        operation=self.operation({"scopes": scopes}, expected=1),
                    )
                self.assertEqual(caught.exception.code, INVALID_INPUT)

    def test_write_scope_is_required_for_write_operations(self) -> None:
        target, _ = self.register("alpha")
        project_id = target["projectId"]
        self.assertEqual(
            self.service.require_project(project_id, scope="read")["projectId"],
            project_id,
        )
        with self.assertRaises(WorkbenchError) as caught:
            self.service.require_project(project_id, scope="write")
        self.assertEqual(caught.exception.code, UNAUTHORIZED)

    def test_capability_can_never_exceed_the_project_grant(self) -> None:
        target, _ = self.register("alpha")
        project_id = target["projectId"]
        self.assertEqual(self.service.capability_plan(project_id, scopes=["read"]), ["read"])
        with self.assertRaises(WorkbenchError):
            self.service.capability_plan(project_id, scopes=["write"])
        with self.assertRaises(WorkbenchError):
            self.service.capability_plan(project_id, scopes=[])
        with self.assertRaises(WorkbenchError):
            self.service.capability_plan(project_id, scopes=["nope"])
        self.service.set_grants(
            project_id,
            scopes=["read", "write"],
            operation=self.operation({"scopes": ["read", "write"]}, expected=0),
        )
        self.assertEqual(
            self.service.capability_plan(project_id, scopes=["write"]), ["write"]
        )


class LifecycleTest(ServiceTestCase):
    def test_open_requires_a_connected_project_and_sets_the_pointer(self) -> None:
        target, _ = self.register("alpha")
        project_id = target["projectId"]
        outcome = self.service.open_project(
            project_id, operation=self.operation({"action": "open"}, expected=0)
        )
        self.assertEqual(outcome["result"]["currentProjectId"], project_id)

    def test_missing_directory_reports_disconnected_and_blocks_operations(self) -> None:
        target, candidate = self.register("alpha")
        project_id = target["projectId"]
        os.rmdir(candidate.canonical_path)
        refreshed = self.service.project_target(project_id)
        self.assertEqual(refreshed["connectionState"], "disconnected")
        with self.assertRaises(WorkbenchError) as caught:
            self.service.require_project(project_id, scope="read")
        self.assertEqual(caught.exception.code, DISCONNECTED)
        with self.assertRaises(WorkbenchError) as caught:
            self.service.open_project(
                project_id, operation=self.operation({"action": "open"}, expected=0)
            )
        self.assertEqual(caught.exception.code, DISCONNECTED)

    def test_rebind_requires_confirmation_and_keeps_the_history(self) -> None:
        target, candidate = self.register("alpha")
        project_id = target["projectId"]
        os.rmdir(candidate.canonical_path)
        replacement = self.directory("alpha-replacement")
        probed = self.service.probe_folder(replacement, exclude_project_id=project_id)
        rebound = self.service.rebind_project(
            project_id,
            path=probed.canonical_path,
            candidate_id=probed.candidate_id,
            operation=self.operation({"action": "rebind"}, expected=0),
        )["result"]
        self.assertEqual(rebound["bindingGeneration"], 2)
        self.assertEqual(rebound["canonicalPath"], str(replacement))
        self.assertEqual(rebound["connectionState"], "connected")
        generations = [row["generation"] for row in self.store.binding_history(project_id)]
        self.assertEqual(generations, [1, 2])

    def test_rebind_cannot_target_another_projects_directory(self) -> None:
        first, _ = self.register("alpha")
        second, second_candidate = self.register("beta")
        with self.assertRaises(WorkbenchError) as caught:
            self.service.rebind_project(
                first["projectId"],
                path=second_candidate.canonical_path,
                candidate_id=second_candidate.candidate_id,
                operation=self.operation({"action": "rebind"}, expected=0),
            )
        self.assertEqual(caught.exception.code, INVALID_TARGET)
        # The second project is untouched by the refused rebind.
        self.assertEqual(
            self.service.project_target(second["projectId"])["bindingGeneration"], 1
        )

    def test_removal_unregisters_without_touching_the_source_directory(self) -> None:
        target, candidate = self.register("alpha")
        project_id = target["projectId"]
        keep = Path(candidate.canonical_path) / "keep-me.txt"
        keep.write_text("maintainer content", encoding="utf-8")
        self.service.open_project(
            project_id, operation=self.operation({"action": "open"}, expected=0)
        )
        outcome = self.service.remove_project(
            project_id, operation=self.operation({"action": "remove"}, expected=0)
        )
        self.assertEqual(outcome["result"], {"removed": project_id})
        self.assertFalse(self.store.project_exists(project_id))
        self.assertTrue(keep.exists())
        self.assertEqual(keep.read_text(encoding="utf-8"), "maintainer content")
        self.assertIsNone(self.store.get_setting("currentProjectId"))
        self.assertIsNone(self.store.active_binding(project_id))

    def test_overview_drops_a_dangling_current_pointer(self) -> None:
        target, _ = self.register("alpha")
        self.store.set_setting("currentProjectId", "00000000-0000-0000-0000-000000000000")
        overview = self.service.projects_overview()
        self.assertIsNone(overview["currentProjectId"])
        self.assertEqual(len(overview["projects"]), 1)


if __name__ == "__main__":  # pragma: no cover - manual run
    unittest.main()
