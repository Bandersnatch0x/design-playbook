#!/usr/bin/env python3
"""A06 (HTTP half): who may propose, who may authorize, and what leaks.

The one thing this file exists to prove is the separation of duties: an
Agent capability holding the write scope can submit a change proposal but
can never approve, recover, revert, or reject one. Everything else here
is the transport face of the domain rules -- digest binding, stale
baselines, recovery blocking, and rejections that echo no path.
"""
from __future__ import annotations

import hashlib
import unittest
from unittest import mock

from design_playbook_workbench import proposals as proposals_module

from tests.harness import WorkbenchHarness

UNKNOWN_PROJECT = "00000000-0000-4000-8000-000000000000"


def digest_of(path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


class ProposalApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.h = WorkbenchHarness()
        self.addCleanup(self.h.stop)
        self.directory = self.h.make_directory("proposal-project")
        self.file = self.directory / "index.html"
        self.file.write_bytes(b"<h1>hello</h1>\n")
        self.project = self.h.register(self.directory, name="Proposal").json["result"]
        self.project_id = self.project["projectId"]
        self.counter = 0

    def grant_write(self) -> None:
        granted = self.h.grant(self.project_id, ["read", "write"], expected_counter=self.counter)
        self.assertEqual(granted.status, 200, granted.text)
        self.counter = granted.json["counter"]

    def capability(self, scopes: list[str]) -> str:
        return self.h.runtime.session.issue_capability(
            project_id=self.project_id, scopes=scopes
        )

    def propose_update(self, content: str = "<h1>updated</h1>\n", **kwargs) -> dict:
        response = self.h.create_proposal(
            self.project_id,
            [
                {
                    "path": "index.html",
                    "operation": "update",
                    "baseHash": digest_of(self.file),
                    "content": content,
                }
            ],
            **kwargs,
        )
        self.assertEqual(response.status, 200, response.text)
        return response.json["result"]

    def read(self) -> str:
        return self.file.read_bytes().decode("utf-8")


class ProposeAndApplyTest(ProposalApiTestCase):
    def test_maintainer_proposes_then_authorizes_the_exact_digest(self) -> None:
        self.grant_write()
        proposal = self.propose_update()
        self.assertEqual(proposal["state"], "awaiting-authorization")
        self.assertEqual(self.read(), "<h1>hello</h1>\n")

        listing = self.h.proposals(self.project_id)
        self.assertEqual(listing.status, 200)
        self.assertEqual(len(listing.json["proposals"]), 1)
        self.assertEqual(
            listing.json["proposals"][0]["proposalId"], proposal["proposalId"]
        )

        detail = self.h.proposal_detail(self.project_id, proposal["proposalId"])
        self.assertEqual(detail.status, 200)
        self.assertIn("-<h1>hello</h1>", detail.json["proposal"]["changes"][0]["diff"])

        applied = self.h.proposal_action(
            self.project_id, proposal["proposalId"], "apply", digest=proposal["digest"]
        )
        self.assertEqual(applied.status, 200, applied.text)
        self.assertEqual(applied.json["result"]["status"], "applied")
        self.assertEqual(self.read(), "<h1>updated</h1>\n")

    def test_a_changed_or_missing_digest_is_a_conflict(self) -> None:
        self.grant_write()
        proposal = self.propose_update()
        for digest in (None, "", "sha256:" + "0" * 64, proposal["digest"] + "x"):
            with self.subTest(digest=digest):
                response = self.h.proposal_action(
                    self.project_id, proposal["proposalId"], "apply", digest=digest
                )
                self.assertEqual(response.status, 409, response.text)
                self.assertEqual(response.error_code, "conflict")
        self.assertEqual(self.read(), "<h1>hello</h1>\n")

    def test_write_scope_is_required_to_propose_and_to_apply(self) -> None:
        readonly = self.h.create_proposal(
            self.project_id,
            [{"path": "new.txt", "operation": "create", "content": "x"}],
        )
        self.assertEqual(readonly.status, 401)
        self.assertEqual(readonly.error_code, "unauthorized")

        self.grant_write()
        proposal = self.propose_update()
        # Drop the write scope again before approving.
        revoked = self.h.grant(self.project_id, ["read"], expected_counter=self.counter)
        self.assertEqual(revoked.status, 200, revoked.text)
        denied = self.h.proposal_action(
            self.project_id, proposal["proposalId"], "apply", digest=proposal["digest"]
        )
        self.assertEqual(denied.status, 401)
        self.assertEqual(self.read(), "<h1>hello</h1>\n")

    def test_baseline_drift_between_review_and_approval_is_refused(self) -> None:
        self.grant_write()
        proposal = self.propose_update()
        self.file.write_bytes(b"<h1>maintainer edit</h1>\n")
        response = self.h.proposal_action(
            self.project_id, proposal["proposalId"], "apply", digest=proposal["digest"]
        )
        self.assertEqual(response.status, 409)
        self.assertEqual(self.read(), "<h1>maintainer edit</h1>\n")

    def test_reject_then_apply_is_refused(self) -> None:
        self.grant_write()
        proposal = self.propose_update()
        rejected = self.h.proposal_action(
            self.project_id, proposal["proposalId"], "reject"
        )
        self.assertEqual(rejected.status, 200, rejected.text)
        self.assertEqual(rejected.json["result"]["state"], "rejected")
        applied = self.h.proposal_action(
            self.project_id, proposal["proposalId"], "apply", digest=proposal["digest"]
        )
        self.assertEqual(applied.status, 409)
        self.assertEqual(self.read(), "<h1>hello</h1>\n")

    def test_revert_produces_a_new_proposal_with_current_baselines(self) -> None:
        self.grant_write()
        proposal = self.propose_update()
        self.assertEqual(
            self.h.proposal_action(
                self.project_id, proposal["proposalId"], "apply", digest=proposal["digest"]
            ).status,
            200,
        )
        revert = self.h.proposal_action(
            self.project_id, proposal["proposalId"], "revert"
        )
        self.assertEqual(revert.status, 200, revert.text)
        revert_proposal = revert.json["result"]
        self.assertNotEqual(
            revert_proposal["proposalId"], proposal["proposalId"]
        )
        self.assertEqual(revert_proposal["state"], "awaiting-authorization")
        self.assertEqual(revert_proposal["changes"][0]["baseHash"], digest_of(self.file))
        self.assertEqual(self.read(), "<h1>updated</h1>\n")
        self.assertEqual(
            self.h.proposal_action(
                self.project_id,
                revert_proposal["proposalId"],
                "apply",
                digest=revert_proposal["digest"],
            ).status,
            200,
        )
        self.assertEqual(self.read(), "<h1>hello</h1>\n")

    def test_unknown_projects_and_proposals_are_invalid_target_without_echo(self) -> None:
        self.grant_write()
        proposal = self.propose_update()
        for project_id, proposal_id in (
            (UNKNOWN_PROJECT, proposal["proposalId"]),
            (self.project_id, UNKNOWN_PROJECT),
        ):
            with self.subTest(proposal_id=proposal_id):
                response = self.h.proposal_action(
                    project_id, proposal_id, "apply", digest=proposal["digest"]
                )
                self.assertEqual(response.status, 400)
                self.assertEqual(response.error_code, "invalid-target")
                self.assertNotIn(UNKNOWN_PROJECT, response.text)

    def test_sensitive_and_escaping_paths_are_refused_without_echo(self) -> None:
        self.grant_write()
        for path in (".git/config", ".env", "id_rsa", "../escape.txt", "C:/hosts"):
            with self.subTest(path=path):
                response = self.h.create_proposal(
                    self.project_id,
                    [{"path": path, "operation": "create", "content": "x"}],
                )
                self.assertEqual(response.status, 400, response.text)
                self.assertNotIn(path, response.text)
        self.assertFalse((self.h.workspace / "escape.txt").exists())


class SeparationOfDutiesTest(ProposalApiTestCase):
    """An Agent capability may propose; only the maintainer may authorize."""

    def setUp(self) -> None:
        super().setUp()
        self.grant_write()

    def test_capability_with_write_scope_may_submit_a_proposal(self) -> None:
        capability = self.capability(["read", "write"])
        response = self.h.create_proposal(
            self.project_id,
            [
                {
                    "path": "index.html",
                    "operation": "update",
                    "baseHash": digest_of(self.file),
                    "content": "<h1>from agent</h1>\n",
                }
            ],
            summary="agent proposal",
            capability=capability,
        )
        self.assertEqual(response.status, 200, response.text)
        self.assertEqual(response.json["result"]["summary"], "agent proposal")
        self.assertEqual(self.read(), "<h1>hello</h1>\n")

    def test_capability_cannot_authorize_recover_revert_or_reject(self) -> None:
        capability = self.capability(["read", "write"])
        proposal = self.propose_update()
        for verb in ("apply", "recover", "revert", "reject"):
            with self.subTest(verb=verb):
                response = self.h.proposal_action(
                    self.project_id,
                    proposal["proposalId"],
                    verb,
                    digest=proposal["digest"],
                    capability=capability,
                )
                self.assertEqual(response.status, 401, response.text)
                self.assertEqual(response.error_code, "unauthorized")
        self.assertEqual(self.read(), "<h1>hello</h1>\n")

    def test_capability_reads_only_its_own_projects_proposals(self) -> None:
        other_directory = self.h.make_directory("other-project")
        other = self.h.register(other_directory, name="Other").json["result"]
        capability = self.capability(["read"])
        own = self.h.proposals(self.project_id, capability=capability)
        self.assertEqual(own.status, 200, own.text)
        foreign = self.h.proposals(other["projectId"], capability=capability)
        self.assertEqual(foreign.status, 401)

    def test_capability_needs_the_write_scope_to_propose(self) -> None:
        capability = self.capability(["read"])
        response = self.h.create_proposal(
            self.project_id,
            [{"path": "new.txt", "operation": "create", "content": "x"}],
            capability=capability,
        )
        self.assertEqual(response.status, 401)
        # Project administration stays closed to any capability.
        renamed = self.h.action(
            self.project_id,
            "rename",
            payload={"name": "Hijacked"},
            expected_counter=self.counter,
            capability=capability,
        )
        self.assertEqual(renamed.status, 401)
        self.assertEqual(
            self.h.projects()["projects"][0]["name"], "Proposal"
        )


class RecoveryHttpTest(ProposalApiTestCase):
    def test_recovery_required_blocks_writes_and_is_reported_by_code(self) -> None:
        self.grant_write()
        proposal = self.propose_update()
        # Force a partial write through the file-write seam, then check the
        # HTTP face: the receipt is never "applied" and writes stay blocked.
        with mock.patch.object(
            proposals_module, "_atomic_replace", side_effect=OSError("injected")
        ):
            failed = self.h.proposal_action(
                self.project_id, proposal["proposalId"], "apply", digest=proposal["digest"]
            )
        self.assertEqual(failed.status, 503)
        self.assertEqual(failed.error_code, "recovery-required")
        self.assertNotIn("applied", failed.text)

        blocked = self.h.create_proposal(
            self.project_id,
            [{"path": "later.txt", "operation": "create", "content": "x"}],
        )
        self.assertEqual(blocked.status, 503)
        self.assertEqual(blocked.error_code, "recovery-required")

        detail = self.h.proposal_detail(self.project_id, proposal["proposalId"])
        self.assertEqual(detail.json["proposal"]["state"], "recovery-required")

        recovered = self.h.proposal_action(
            self.project_id, proposal["proposalId"], "recover", mode="rollback"
        )
        self.assertEqual(recovered.status, 200, recovered.text)
        self.assertEqual(recovered.json["result"]["status"], "rolled-back")
        self.assertEqual(self.read(), "<h1>hello</h1>\n")

        # With recovery done, a new proposal applies normally again.
        second = self.propose_update("<h1>after recovery</h1>\n")
        self.assertEqual(
            self.h.proposal_action(
                self.project_id, second["proposalId"], "apply", digest=second["digest"]
            ).status,
            200,
        )
        self.assertEqual(self.read(), "<h1>after recovery</h1>\n")


if __name__ == "__main__":  # pragma: no cover - manual run
    unittest.main()
