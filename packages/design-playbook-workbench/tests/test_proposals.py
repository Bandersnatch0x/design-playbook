#!/usr/bin/env python3
"""A06 (domain half): proposals, authorized apply, and recovery.

Uses real temporary directories and a real database, and injects
failures at the file-write seam so the ``recovery-required`` path is
exercised for real: a partial multi-file write must never report
``applied``, and recovery must be an explicit, hash-checked decision that
never overwrites the maintainer's own edits.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from design_playbook_workbench import proposals as proposals_module
from design_playbook_workbench.errors import (
    CONFLICT,
    INVALID_INPUT,
    INVALID_TARGET,
    LIMIT_EXCEEDED,
    RECOVERY_REQUIRED,
    UNAUTHORIZED,
    WorkbenchError,
)
from design_playbook_workbench.proposals import (
    JOURNAL_RECOVERY,
    JOURNAL_ROLLED_BACK,
    STATE_APPLIED,
    STATE_AWAITING,
    STATE_RECOVERY,
    STATE_REJECTED,
    ProposalService,
    sha256_bytes,
)
from design_playbook_workbench.service import Operation, WorkbenchService
from design_playbook_workbench.store import Store, WorkbenchDataDirectory


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 9, 26, 12, 0, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs) -> None:
        self.now = self.now + timedelta(**kwargs)


class ProposalTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name).resolve()
        self._operations = 0
        self.data_dir = WorkbenchDataDirectory(self.base / "data").ensure()
        self.store = Store(self.data_dir.database_path)
        self.clock = Clock()
        self.service = WorkbenchService(store=self.store, data_dir=self.data_dir)
        self.proposals = ProposalService(
            store=self.store,
            service=self.service,
            data_dir=self.data_dir,
            now_fn=self.clock,
        )
        self.project = self.base / "project"
        self.project.mkdir()
        # Bytes, not text: text-mode writes would translate newlines on
        # Windows and the baseline hashes below must match the real bytes.
        (self.project / "index.html").write_bytes(b"<h1>hello</h1>\n")
        (self.project / "app.css").write_bytes(b"body { color: black; }\n")
        candidate = self.service.probe_folder(self.project)
        self.target = self.service.register_project(
            path=candidate.canonical_path,
            candidate_id=candidate.candidate_id,
            name="Project",
            operation=self.operation({"action": "register-project"}),
        )["result"]
        self.project_id = self.target["projectId"]
        self.grant_write()

    def tearDown(self) -> None:
        self.store.close()
        self._tmp.cleanup()

    def operation(self, payload: dict, *, expected: int | None = None, operation_id: str | None = None):
        if operation_id is None:
            self._operations += 1
            operation_id = f"op_prop_{self._operations:08d}"
        return Operation(
            operation_id=operation_id, payload=payload, expected_counter=expected
        )

    def grant_write(self) -> None:
        counter = int(self.store.project(self.project_id)["counter"])
        self.service.set_grants(
            self.project_id,
            scopes=["read", "write"],
            operation=self.operation({"scopes": ["read", "write"]}, expected=counter),
        )

    def create(self, changes: list[dict], *, summary: str = "", operation: Operation | None = None):
        return self.proposals.create(
            self.project_id,
            changes=changes,
            summary=summary,
            operation=operation or self.operation({"changes": changes}),
        )["result"]

    def apply(self, proposal: dict, *, digest: str | None = None, operation: Operation | None = None):
        return self.proposals.apply(
            self.project_id,
            proposal["proposalId"],
            digest=proposal["digest"] if digest is None else digest,
            operation=operation or self.operation({"apply": proposal["proposalId"]}),
        )["result"]

    def read(self, name: str) -> str:
        return (self.project / name).read_bytes().decode("utf-8")

    def digest_of(self, name: str) -> str:
        return sha256_bytes((self.project / name).read_bytes())

    def write(self, name: str, text: str) -> None:
        (self.project / name).write_bytes(text.encode("utf-8"))


class ProposalCreationTest(ProposalTestCase):
    def test_proposal_records_diff_hashes_and_digest(self) -> None:
        proposal = self.create(
            [
                {"path": "index.html", "operation": "update",
                 "baseHash": self.digest_of("index.html"),
                 "content": "<h1>updated</h1>\n"},
                {"path": "styles/tokens.css", "operation": "create",
                 "content": ":root { --gap: 8px; }\n"},
                {"path": "app.css", "operation": "delete",
                 "baseHash": self.digest_of("app.css")},
            ],
            summary="revise shell",
        )
        self.assertEqual(proposal["state"], STATE_AWAITING)
        self.assertTrue(proposal["digest"].startswith("sha256:"))
        self.assertEqual(len(proposal["changes"]), 3)
        by_path = {change["path"]: change for change in proposal["changes"]}
        self.assertIn("-<h1>hello</h1>", by_path["index.html"]["diff"])
        self.assertIn("+<h1>updated</h1>", by_path["index.html"]["diff"])
        self.assertIn("--- /dev/null", by_path["styles/tokens.css"]["diff"])
        self.assertIn("+++ b/styles/tokens.css", by_path["styles/tokens.css"]["diff"])
        self.assertIsNone(by_path["app.css"]["resultHash"])
        # Nothing is written into the project by creating a proposal.
        self.assertEqual(self.read("index.html"), "<h1>hello</h1>\n")
        self.assertTrue((self.project / "app.css").exists())
        self.assertFalse((self.project / "styles").exists())
        # The digest binds the target and every operation.
        digest_again = self.create(
            [
                {"path": "index.html", "operation": "update",
                 "baseHash": self.digest_of("index.html"),
                 "content": "<h1>updated</h1>\n"},
                {"path": "styles/tokens.css", "operation": "create",
                 "content": ":root { --gap: 8px; }\n"},
                {"path": "app.css", "operation": "delete",
                 "baseHash": self.digest_of("app.css")},
            ]
        )
        self.assertEqual(proposal["digest"], digest_again["digest"])

    def test_wrong_baseline_is_refused_at_creation(self) -> None:
        with self.assertRaises(WorkbenchError) as caught:
            self.create(
                [
                    {"path": "index.html", "operation": "update",
                     "baseHash": "sha256:" + "0" * 64, "content": "x"},
                ]
            )
        self.assertEqual(caught.exception.code, CONFLICT)

    def test_creating_an_existing_file_or_updating_a_missing_one_is_refused(self) -> None:
        with self.assertRaises(WorkbenchError) as caught:
            self.create([{"path": "index.html", "operation": "create", "content": "x"}])
        self.assertEqual(caught.exception.code, CONFLICT)
        with self.assertRaises(WorkbenchError) as caught:
            self.create(
                [
                    {"path": "missing.html", "operation": "update",
                     "baseHash": "sha256:" + "0" * 64, "content": "x"},
                ]
            )
        self.assertEqual(caught.exception.code, CONFLICT)

    def test_write_scope_is_required_to_propose(self) -> None:
        counter = int(self.store.project(self.project_id)["counter"])
        self.service.set_grants(
            self.project_id,
            scopes=["read"],
            operation=self.operation({"scopes": ["read"]}, expected=counter),
        )
        with self.assertRaises(WorkbenchError) as caught:
            self.create([{"path": "new.html", "operation": "create", "content": "x"}])
        self.assertEqual(caught.exception.code, UNAUTHORIZED)

    def test_paths_outside_the_project_and_sensitive_files_are_refused(self) -> None:
        for path in (
            "../escape.html",
            "/absolute.html",
            "C:/windows/system32/drivers/etc/hosts",
            "nested/../../escape.html",
            ".git/config",
            "sub/.git/config",
            ".env",
            ".env.local",
            "id_rsa",
            "secrets/cert.pem",
            "private.key",
            "",
            "   ",
            "nested//double.html",
        ):
            with self.subTest(path=path):
                with self.assertRaises(WorkbenchError) as caught:
                    self.create([{"path": path, "operation": "create", "content": "x"}])
                self.assertIn(
                    caught.exception.code, (INVALID_TARGET, INVALID_INPUT)
                )
        self.assertFalse((self.base / "escape.html").exists())

    def test_junction_inside_the_project_cannot_escape(self) -> None:
        from tests.harness import make_directory_link

        outside = self.base / "outside"
        outside.mkdir()
        link = self.project / "shared"
        if not make_directory_link(link, outside):
            self.skipTest("directory links are unavailable on this host")
        with self.assertRaises(WorkbenchError) as caught:
            self.create(
                [{"path": "shared/escape.html", "operation": "create", "content": "x"}]
            )
        self.assertEqual(caught.exception.code, INVALID_TARGET)
        self.assertFalse((outside / "escape.html").exists())

    def test_limits_are_enforced(self) -> None:
        too_many = [
            {"path": f"file-{index}.txt", "operation": "create", "content": "x"}
            for index in range(60)
        ]
        with self.assertRaises(WorkbenchError) as caught:
            self.create(too_many)
        self.assertEqual(caught.exception.code, LIMIT_EXCEEDED)
        with self.assertRaises(WorkbenchError) as caught:
            self.create(
                [{"path": "big.txt", "operation": "create", "content": "x" * (1024 * 1024 + 1)}]
            )
        self.assertEqual(caught.exception.code, LIMIT_EXCEEDED)

    def test_unknown_operations_and_shapes_are_invalid_input(self) -> None:
        for changes in (
            [],
            None,
            "x",
            [{"path": "a.txt", "operation": "replace", "content": "x"}],
            [{"path": "a.txt", "operation": "create"}],
            [{"path": "a.txt", "operation": "delete"}],
            [{"path": "a.txt", "operation": "update", "content": "x"}],
            [{"path": "a.txt", "operation": "create", "content": 5}],
            [{"path": "a.txt", "operation": "create", "content": "x"},
             {"path": "a.txt", "operation": "create", "content": "y"}],
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(WorkbenchError) as caught:
                    self.create(changes)
                self.assertEqual(caught.exception.code, INVALID_INPUT)


class ApplyTest(ProposalTestCase):
    def test_multi_file_apply_writes_every_file_and_reports_result_hashes(self) -> None:
        proposal = self.create(
            [
                {"path": "index.html", "operation": "update",
                 "baseHash": self.digest_of("index.html"),
                 "content": "<h1>updated</h1>\n"},
                {"path": "styles/tokens.css", "operation": "create",
                 "content": ":root { --gap: 8px; }\n"},
                {"path": "app.css", "operation": "delete",
                 "baseHash": self.digest_of("app.css")},
            ]
        )
        receipt = self.apply(proposal)
        self.assertEqual(receipt["status"], "applied")
        self.assertEqual(self.read("index.html"), "<h1>updated</h1>\n")
        self.assertEqual(
            (self.project / "styles" / "tokens.css").read_text(encoding="utf-8"),
            ":root { --gap: 8px; }\n",
        )
        self.assertFalse((self.project / "app.css").exists())
        for path, digest in receipt["resultHashes"].items():
            if digest is None:
                self.assertFalse((self.project / path).exists())
            else:
                self.assertEqual(
                    sha256_bytes((self.project / path).read_bytes()), digest
                )
        # No temporary file and no version-control side effect is left behind.
        leftovers = [item.name for item in self.project.rglob("*") if item.is_file()
                     and item.name.startswith(".")]
        self.assertEqual(leftovers, [])
        self.assertFalse((self.project / ".git").exists())
        detail = self.proposals.detail(self.project_id, proposal["proposalId"])
        self.assertEqual(detail["proposal"]["state"], STATE_APPLIED)

    def test_apply_is_idempotent_for_the_same_operation_id(self) -> None:
        proposal = self.create(
            [{"path": "new.txt", "operation": "create", "content": "one\n"}]
        )
        operation = self.operation({"apply": proposal["proposalId"]}, operation_id="op_apply_once_1")
        first = self.proposals.apply(
            self.project_id, proposal["proposalId"], digest=proposal["digest"], operation=operation
        )
        second = self.proposals.apply(
            self.project_id, proposal["proposalId"], digest=proposal["digest"], operation=operation
        )
        self.assertFalse(first["replayed"])
        self.assertTrue(second["replayed"])
        self.assertEqual(first["result"], second["result"])
        self.assertEqual((self.project / "new.txt").read_text(encoding="utf-8"), "one\n")
        self.assertIsNotNone(self.store.journal(proposal["proposalId"]))

    def test_changed_digest_or_expired_proposal_is_refused(self) -> None:
        proposal = self.create(
            [{"path": "new.txt", "operation": "create", "content": "one\n"}]
        )
        with self.assertRaises(WorkbenchError) as caught:
            self.apply(proposal, digest="sha256:" + "1" * 64)
        self.assertEqual(caught.exception.code, CONFLICT)
        self.assertFalse((self.project / "new.txt").exists())

        self.clock.advance(minutes=31)
        with self.assertRaises(WorkbenchError) as caught:
            self.apply(proposal)
        self.assertEqual(caught.exception.code, CONFLICT)
        self.assertEqual(
            self.proposals.detail(self.project_id, proposal["proposalId"])["proposal"]["state"],
            "expired",
        )
        self.assertFalse((self.project / "new.txt").exists())

    def test_baseline_drift_after_creation_blocks_the_write(self) -> None:
        proposal = self.create(
            [
                {"path": "index.html", "operation": "update",
                 "baseHash": self.digest_of("index.html"),
                 "content": "<h1>from proposal</h1>\n"},
            ]
        )
        # The maintainer edits the file between review and application.
        self.write("index.html", "<h1>local edit</h1>\n")
        with self.assertRaises(WorkbenchError) as caught:
            self.apply(proposal)
        self.assertEqual(caught.exception.code, CONFLICT)
        self.assertEqual(self.read("index.html"), "<h1>local edit</h1>\n")

    def test_create_precondition_is_rechecked(self) -> None:
        proposal = self.create(
            [{"path": "new.txt", "operation": "create", "content": "one\n"}]
        )
        self.write("new.txt", "something else\n")
        with self.assertRaises(WorkbenchError) as caught:
            self.apply(proposal)
        self.assertEqual(caught.exception.code, CONFLICT)
        self.assertEqual(
            (self.project / "new.txt").read_text(encoding="utf-8"), "something else\n"
        )

    def test_rebinding_after_creation_blocks_the_write(self) -> None:
        proposal = self.create(
            [{"path": "new.txt", "operation": "create", "content": "one\n"}]
        )
        moved = self.base / "moved-project"
        os.rename(self.project, moved)
        candidate = self.service.probe_folder(moved, exclude_project_id=self.project_id)
        counter = int(self.store.project(self.project_id)["counter"])
        self.service.rebind_project(
            self.project_id,
            path=candidate.canonical_path,
            candidate_id=candidate.candidate_id,
            operation=self.operation({"action": "rebind"}, expected=counter),
        )
        with self.assertRaises(WorkbenchError) as caught:
            self.apply(proposal)
        self.assertEqual(caught.exception.code, CONFLICT)
        self.assertFalse((moved / "new.txt").exists())

    def test_reject_then_apply_is_refused(self) -> None:
        proposal = self.create(
            [{"path": "new.txt", "operation": "create", "content": "one\n"}]
        )
        rejected = self.proposals.reject(
            self.project_id, proposal["proposalId"], operation=self.operation({"reject": 1})
        )["result"]
        self.assertEqual(rejected["state"], STATE_REJECTED)
        with self.assertRaises(WorkbenchError) as caught:
            self.apply(proposal)
        self.assertEqual(caught.exception.code, CONFLICT)
        self.assertFalse((self.project / "new.txt").exists())


class CrashRecoveryTest(ProposalTestCase):
    def _crashing_replace(self, fail_on_call: int):
        original = proposals_module._atomic_replace
        calls = {"count": 0}

        def wrapper(path, data):
            calls["count"] += 1
            if calls["count"] == fail_on_call:
                raise OSError("injected write failure")
            return original(path, data)

        return wrapper

    def test_partial_write_never_reports_applied_and_blocks_new_writes(self) -> None:
        proposal = self.create(
            [
                {"path": "one.txt", "operation": "create", "content": "1\n"},
                {"path": "two.txt", "operation": "create", "content": "2\n"},
                {"path": "three.txt", "operation": "create", "content": "3\n"},
            ]
        )
        with mock.patch.object(
            proposals_module, "_atomic_replace", side_effect=self._crashing_replace(3)
        ):
            with self.assertRaises(WorkbenchError) as caught:
                self.apply(proposal)
        self.assertEqual(caught.exception.code, RECOVERY_REQUIRED)
        # Two files landed, the third did not: the receipt says nothing.
        self.assertTrue((self.project / "one.txt").exists())
        self.assertTrue((self.project / "two.txt").exists())
        self.assertFalse((self.project / "three.txt").exists())
        journal = self.store.journal(proposal["proposalId"])
        self.assertEqual(journal["state"], JOURNAL_RECOVERY)
        self.assertEqual(
            self.proposals.detail(self.project_id, proposal["proposalId"])["proposal"]["state"],
            STATE_RECOVERY,
        )
        # Every new write for this project is blocked until recovery runs.
        with self.assertRaises(WorkbenchError) as caught:
            self.create([{"path": "other.txt", "operation": "create", "content": "x"}])
        self.assertEqual(caught.exception.code, RECOVERY_REQUIRED)

    def test_rollback_restores_the_previous_bytes_and_unblocks_writes(self) -> None:
        original_index = self.read("index.html")
        proposal = self.create(
            [
                {"path": "one.txt", "operation": "create", "content": "1\n"},
                {"path": "index.html", "operation": "update",
                 "baseHash": self.digest_of("index.html"),
                 "content": "<h1>from proposal</h1>\n"},
                {"path": "two.txt", "operation": "create", "content": "2\n"},
                {"path": "app.css", "operation": "delete",
                 "baseHash": self.digest_of("app.css")},
            ]
        )
        # Fail on the third file write: the first two land, the rest do not.
        with mock.patch.object(
            proposals_module, "_atomic_replace", side_effect=self._crashing_replace(3)
        ):
            with self.assertRaises(WorkbenchError):
                self.apply(proposal)
        self.assertTrue((self.project / "one.txt").exists())
        self.assertEqual(self.read("index.html"), "<h1>from proposal</h1>\n")
        self.assertFalse((self.project / "two.txt").exists())
        self.assertTrue((self.project / "app.css").exists())

        receipt = self.proposals.recover(
            self.project_id,
            proposal["proposalId"],
            mode="rollback",
            operation=self.operation({"recover": "rollback"}),
        )["result"]
        self.assertEqual(receipt["status"], "rolled-back")
        self.assertEqual(self.read("index.html"), original_index)
        self.assertTrue((self.project / "app.css").exists())
        self.assertFalse((self.project / "one.txt").exists())
        self.assertFalse((self.project / "two.txt").exists())
        self.assertEqual(
            self.store.journal(proposal["proposalId"])["state"], JOURNAL_ROLLED_BACK
        )
        # Writes are possible again, and a fresh proposal can be applied.
        second = self.create(
            [{"path": "after.txt", "operation": "create", "content": "ok\n"}]
        )
        self.apply(second)
        self.assertEqual((self.project / "after.txt").read_text(encoding="utf-8"), "ok\n")

    def test_recovery_finish_completes_the_remaining_writes(self) -> None:
        proposal = self.create(
            [
                {"path": "one.txt", "operation": "create", "content": "1\n"},
                {"path": "two.txt", "operation": "create", "content": "2\n"},
                {"path": "three.txt", "operation": "create", "content": "3\n"},
            ]
        )
        with mock.patch.object(
            proposals_module, "_atomic_replace", side_effect=self._crashing_replace(2)
        ):
            with self.assertRaises(WorkbenchError):
                self.apply(proposal)
        self.assertTrue((self.project / "one.txt").exists())
        self.assertFalse((self.project / "two.txt").exists())
        receipt = self.proposals.recover(
            self.project_id,
            proposal["proposalId"],
            mode="finish",
            operation=self.operation({"recover": "finish"}),
        )["result"]
        self.assertEqual(receipt["status"], "applied")
        for name in ("one.txt", "two.txt", "three.txt"):
            self.assertTrue((self.project / name).exists(), name)

    def test_recovery_refuses_to_overwrite_an_external_edit(self) -> None:
        proposal = self.create(
            [
                {"path": "one.txt", "operation": "create", "content": "1\n"},
                {"path": "two.txt", "operation": "create", "content": "2\n"},
            ]
        )
        with mock.patch.object(
            proposals_module, "_atomic_replace", side_effect=self._crashing_replace(2)
        ):
            with self.assertRaises(WorkbenchError):
                self.apply(proposal)
        # The maintainer edits the file the failed run produced.
        self.write("one.txt", "maintainer edit\n")
        with self.assertRaises(WorkbenchError) as caught:
            self.proposals.recover(
                self.project_id,
                proposal["proposalId"],
                mode="rollback",
                operation=self.operation({"recover": "rollback"}),
            )
        self.assertEqual(caught.exception.code, CONFLICT)
        self.assertEqual(
            (self.project / "one.txt").read_text(encoding="utf-8"), "maintainer edit\n"
        )
        self.assertEqual(
            self.store.journal(proposal["proposalId"])["state"], JOURNAL_RECOVERY
        )

    def test_recovery_rejects_an_unknown_mode_and_a_missing_journal(self) -> None:
        proposal = self.create(
            [{"path": "one.txt", "operation": "create", "content": "1\n"}]
        )
        with self.assertRaises(WorkbenchError) as caught:
            self.proposals.recover(
                self.project_id,
                proposal["proposalId"],
                mode="nonsense",
                operation=self.operation({"recover": "nonsense"}),
            )
        self.assertEqual(caught.exception.code, INVALID_INPUT)
        with self.assertRaises(WorkbenchError) as caught:
            self.proposals.recover(
                self.project_id,
                proposal["proposalId"],
                mode="rollback",
                operation=self.operation({"recover": "rollback"}),
            )
        self.assertEqual(caught.exception.code, CONFLICT)


class RevertTest(ProposalTestCase):
    def test_revert_creates_a_new_proposal_bound_to_current_hashes(self) -> None:
        original_index = self.read("index.html")
        proposal = self.create(
            [
                {"path": "index.html", "operation": "update",
                 "baseHash": self.digest_of("index.html"),
                 "content": "<h1>from proposal</h1>\n"},
                {"path": "new.txt", "operation": "create", "content": "created\n"},
            ]
        )
        self.apply(proposal)
        self.assertEqual(self.read("index.html"), "<h1>from proposal</h1>\n")

        revert = self.proposals.revert(
            self.project_id, proposal["proposalId"], operation=self.operation({"revert": 1})
        )["result"]
        self.assertEqual(revert["state"], STATE_AWAITING)
        self.assertNotEqual(revert["proposalId"], proposal["proposalId"])
        by_path = {change["path"]: change for change in revert["changes"]}
        self.assertEqual(by_path["index.html"]["operation"], "update")
        self.assertEqual(by_path["index.html"]["baseHash"], self.digest_of("index.html"))
        self.assertEqual(by_path["new.txt"]["operation"], "delete")
        # The revert only becomes real when the maintainer authorizes it.
        self.assertEqual(self.read("index.html"), "<h1>from proposal</h1>\n")
        self.apply(revert)
        self.assertEqual(self.read("index.html"), original_index)
        self.assertFalse((self.project / "new.txt").exists())

    def test_retrying_a_revert_replays_instead_of_conflicting(self) -> None:
        proposal = self.create(
            [{"path": "new.txt", "operation": "create", "content": "created\n"}]
        )
        self.apply(proposal)
        op = self.operation({"revert": 9}, operation_id="op_revert_retry")
        first = self.proposals.revert(
            self.project_id, proposal["proposalId"], operation=op
        )
        # Same operation-id + digest: the retry must replay the staged revert
        # proposal, not raise CONFLICT and not stage a duplicate.
        second = self.proposals.revert(
            self.project_id, proposal["proposalId"], operation=op
        )
        self.assertFalse(first["replayed"])
        self.assertTrue(second["replayed"])
        self.assertEqual(
            first["result"]["proposalId"], second["result"]["proposalId"]
        )
        revert_ids = {
            row["proposalId"]
            for row in self.proposals.list_for_project(self.project_id)["proposals"]
            if row["proposalId"] != proposal["proposalId"]
        }
        self.assertEqual(len(revert_ids), 1)

    def test_revert_is_refused_when_the_file_changed_after_apply(self) -> None:
        proposal = self.create(
            [{"path": "new.txt", "operation": "create", "content": "created\n"}]
        )
        self.apply(proposal)
        self.write("new.txt", "maintainer edit\n")
        with self.assertRaises(WorkbenchError) as caught:
            self.proposals.revert(
                self.project_id, proposal["proposalId"], operation=self.operation({"revert": 2})
            )
        self.assertEqual(caught.exception.code, CONFLICT)

    def test_revert_before_apply_is_refused(self) -> None:
        proposal = self.create(
            [{"path": "new.txt", "operation": "create", "content": "created\n"}]
        )
        with self.assertRaises(WorkbenchError) as caught:
            self.proposals.revert(
                self.project_id, proposal["proposalId"], operation=self.operation({"revert": 3})
            )
        self.assertEqual(caught.exception.code, CONFLICT)


class FileOccupancyTest(ProposalTestCase):
    def test_a_locked_target_file_is_never_a_silent_partial_success(self) -> None:
        """Windows holds a mandatory lock; POSIX replace ignores it.

        The point is the same on both: a failure to write reports
        ``recovery-required`` and blocks further writes, and the platform
        difference is stated rather than papered over.
        """
        proposal = self.create(
            [
                {"path": "index.html", "operation": "update",
                 "baseHash": self.digest_of("index.html"),
                 "content": "<h1>updated</h1>\n"},
            ]
        )
        with open(self.project / "index.html", "r+", encoding="utf-8") as handle:
            handle.read()
            if os.name == "nt":
                with self.assertRaises(WorkbenchError) as caught:
                    self.apply(proposal)
                self.assertEqual(caught.exception.code, RECOVERY_REQUIRED)
                self.assertEqual(self.read("index.html"), "<h1>hello</h1>\n")
                journal = self.store.journal(proposal["proposalId"])
                self.assertEqual(journal["state"], JOURNAL_RECOVERY)
            else:
                self.apply(proposal)
                self.assertEqual(self.read("index.html"), "<h1>updated</h1>\n")
        if os.name == "nt":
            # With the handle released, recovery restores the previous bytes.
            self.proposals.recover(
                self.project_id,
                proposal["proposalId"],
                mode="rollback",
                operation=self.operation({"recover": "locked"}),
            )
            self.assertEqual(self.read("index.html"), "<h1>hello</h1>\n")


if __name__ == "__main__":  # pragma: no cover - manual run
    unittest.main()
