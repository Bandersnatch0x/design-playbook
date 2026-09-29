#!/usr/bin/env python3
"""A11 over the real API: consent, agent traffic, cancel, and approval bounds.

The domain rules live in ``test_work.py``; these tests prove the transport
surface: a request-bound capability can claim/report only its own request,
maintainer-only verbs refuse a capability even with the write scope, an
Agent can never approve its own proposal, and no response leaks the token.
"""
from __future__ import annotations

import json
import unittest

from tests.harness import WorkbenchHarness, http_request

CANVAS = {
    "name": "任务画布",
    "boards": [
        {
            "id": "b1",
            "name": "首页",
            "width": 1200,
            "height": 800,
            "nodes": [
                {"id": "n1", "type": "stack", "children": ["n2"], "props": {},
                 "layout": {"x": 40, "y": 40, "width": 600, "height": 400, "z": 0}},
                {"id": "n2", "type": "text", "children": [], "props": {"text": "标题"},
                 "layout": {"x": 60, "y": 60, "width": 320, "height": 40, "z": 1}},
            ],
            "flowEdges": [],
            "scheme": None,
        }
    ],
}


class WorkApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.h = WorkbenchHarness()
        self.addCleanup(self.h.stop)
        self._operations = 0
        self.project_dir = self.h.make_directory("work")
        self.other_dir = self.h.make_directory("other")
        self.registered = self.h.register(self.project_dir, name="Design").json["result"]
        self.other = self.h.register(self.other_dir, name="Other").json["result"]
        self.project_id = self.registered["projectId"]
        self.other_id = self.other["projectId"]
        self.grant(self.project_id, ["read", "write"])
        self.grant(self.other_id, ["read", "write"])
        created = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.project_id}/actions/canvases",
            method="POST",
            body={
                "operation": {
                    "operationId": "op_api_work_canvas",
                    "payload": {"action": "canvases"},
                },
                "name": "任务画布",
                "document": CANVAS,
            },
            token=self.h.token,
            origin=self.h.runtime.origin,
        )
        assert created.status == 200, created.text
        self.canvas_id = created.json["result"]["canvas"]["canvasId"]
        self.selection = self.build_and_confirm_context()

    # -- helpers ---------------------------------------------------------

    def grant(self, project_id: str, scopes: list[str]) -> None:
        counter = self.h.project_target(project_id)["counter"]
        assert self.h.grant(project_id, scopes, expected_counter=counter).status == 200

    def capability(self, project_id: str, scopes: list[str]) -> str:
        return self.h.runtime.session.issue_capability(
            project_id=project_id, scopes=scopes
        )

    def build_and_confirm_context(self) -> dict:
        built = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.project_id}/actions/canvases/"
            f"{self.canvas_id}/contexts",
            method="POST",
            body={
                "operation": {
                    "operationId": "op_api_work_context",
                    "payload": {"action": "contexts"},
                },
                "boardId": "b1",
                "nodeIds": ["n2"],
            },
            token=self.h.token,
            origin=self.h.runtime.origin,
        )
        assert built.status == 200, built.text
        selection = built.json["result"]
        confirmed = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.project_id}/actions/canvases/"
            f"{self.canvas_id}/confirm",
            method="POST",
            body={
                "operation": {
                    "operationId": "op_api_work_confirm",
                    "payload": {"action": "confirm"},
                },
                "selectionId": selection["selectionId"],
                "digest": selection["digest"],
            },
            token=self.h.token,
            origin=self.h.runtime.origin,
        )
        assert confirmed.status == 200, confirmed.text
        return confirmed.json["result"]

    def request_action(
        self,
        verb: str,
        *,
        request_id: str | None = None,
        payload: dict | None = None,
        capability: str | None = None,
        operation_id: str | None = None,
        project_id: str | None = None,
    ):
        self._operations += 1
        operation = {
            "operationId": operation_id or f"op_api_work_{self._operations:04d}",
            "payload": {"action": verb, **(payload or {})},
        }
        path = (
            f"/api/v1/projects/{project_id or self.project_id}/actions/requests/"
            f"{request_id}/{verb}"
            if request_id
            else f"/api/v1/projects/{project_id or self.project_id}/actions/requests"
        )
        return http_request(
            self.h.runtime,
            path,
            method="POST",
            body={"operation": operation, **(payload or {})},
            token=None if capability else self.h.token,
            capability=capability,
            origin=None if capability else self.h.runtime.origin,
        )

    def create_request(self, **overrides) -> dict:
        payload = {
            "title": "首页静态改版",
            "goal": "改写标题",
            "targetStack": "static-html",
            "contextSelectionId": self.selection["selectionId"],
            "plan": {"reuse": ["首页布局"], "adapt": [], "new": ["标题文案"]},
            "allowedActions": ["read-context", "propose-source"],
        }
        payload.update(overrides)
        response = self.request_action("requests", payload=payload)
        assert response.status == 200, response.text
        return response.json["result"]

    def claim_record(self, request_id: str) -> dict:
        path = self.h.runtime.data_dir.session_dir / f"claim-{request_id}.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def claim_and_report(self, request: dict):
        lease = self.request_action(
            "claim", request_id=request["requestId"], capability=self.agent_token(request)
        )
        assert lease.status == 200, lease.text
        return lease.json["result"]

    def agent_token(self, request: dict) -> str:
        return self.claim_record(request["requestId"])["token"]


class RequestLifecycleApiTest(WorkApiTestCase):
    def test_create_read_and_consent_over_the_api(self) -> None:
        request = self.create_request()
        self.assertEqual(request["state"], "awaiting-consent")
        listing = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.project_id}/requests",
            token=self.h.token,
        )
        self.assertEqual(listing.status, 200, listing.text)
        self.assertEqual(len(listing.json["requests"]), 1)
        detail = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.project_id}/requests/{request['requestId']}",
            token=self.h.token,
        )
        self.assertEqual(detail.status, 200, detail.text)
        payload = detail.json["request"]
        self.assertEqual(payload["contextSelectionId"], self.selection["selectionId"])
        self.assertTrue(payload["contextStillConfirmed"])
        self.assertEqual(payload["attempts"], [])
        self.assertNotIn("token", json.dumps(detail.json))

        consented = self.request_action(
            "consent",
            request_id=request["requestId"],
            payload={"digest": request["contextDigest"]},
        )
        self.assertEqual(consented.status, 200, consented.text)
        self.assertEqual(consented.json["result"]["state"], "waiting-for-agent")
        self.assertIn("/design-playbook:run-handoff", consented.json["result"]["handoffCommand"])
        # The token stays in the private record, never in a response.
        token = self.claim_record(request["requestId"])["token"]
        self.assertNotIn(token, consented.text)
        self.assertNotIn(token, json.dumps(detail.json))

        # Consent is a maintainer decision: a write capability is refused.
        second = self.create_request(title="第二个任务")
        denied = self.request_action(
            "consent",
            request_id=second["requestId"],
            payload={"digest": second["contextDigest"]},
            capability=self.capability(self.project_id, ["read", "write"]),
        )
        self.assertEqual(denied.status, 401)

    def test_a_capability_cannot_reach_the_agent_verbs(self) -> None:
        request = self.create_request()
        self.request_action(
            "consent",
            request_id=request["requestId"],
            payload={"digest": request["contextDigest"]},
        )
        plain = self.capability(self.project_id, ["read", "write"])
        for verb in ("claim", "heartbeat", "result", "fail"):
            with self.subTest(verb=verb):
                response = self.request_action(
                    verb,
                    request_id=request["requestId"],
                    payload={"attemptId": "x", "leaseId": "y", "sequence": 1},
                    capability=plain,
                )
                self.assertEqual(response.status, 401, response.text)
        # The browser session is not an Agent credential either.
        browser_claim = self.request_action("claim", request_id=request["requestId"])
        self.assertEqual(browser_claim.status, 401)


class AgentTrafficApiTest(WorkApiTestCase):
    def test_claim_heartbeat_result_and_maintainer_approval(self) -> None:
        request = self.create_request()
        self.request_action(
            "consent",
            request_id=request["requestId"],
            payload={"digest": request["contextDigest"]},
        )
        token = self.agent_token(request)
        claimed = self.claim_and_report(request)
        lease = claimed["lease"]
        self.assertEqual(lease["sequence"], 1)
        self.assertEqual(claimed["state"], "running")

        # A capability bound to another request cannot drive this one.
        other = self.create_request(title="另一个任务")
        self.request_action(
            "consent",
            request_id=other["requestId"],
            payload={"digest": other["contextDigest"]},
        )
        foreign = self.agent_token(other)
        crossed = self.request_action(
            "claim",
            request_id=request["requestId"],
            capability=foreign,
        )
        self.assertEqual(crossed.status, 401)

        beat = self.request_action(
            "heartbeat",
            request_id=request["requestId"],
            payload={
                "attemptId": lease["attemptId"],
                "leaseId": lease["leaseId"],
                "sequence": lease["sequence"],
                "progress": {"phase": "editing"},
            },
            capability=token,
        )
        self.assertEqual(beat.status, 200, beat.text)
        wrong_sequence = self.request_action(
            "heartbeat",
            request_id=request["requestId"],
            payload={
                "attemptId": lease["attemptId"],
                "leaseId": lease["leaseId"],
                "sequence": 9,
            },
            capability=token,
        )
        self.assertEqual(wrong_sequence.status, 409)
        self.assertEqual(wrong_sequence.error_code, "conflict")

        submitted = self.request_action(
            "result",
            request_id=request["requestId"],
            payload={
                "attemptId": lease["attemptId"],
                "leaseId": lease["leaseId"],
                "sequence": lease["sequence"],
                "result": {
                    "summary": "改写标题",
                    "targetStack": "static-html",
                    "changes": [
                        {"path": "index.html", "operation": "create",
                         "content": "<h1>新标题</h1>\n"}
                    ],
                    "dependencies": [],
                    "entrypoints": {"preview": "index.html"},
                    "artifacts": [],
                },
            },
            capability=token,
        )
        self.assertEqual(submitted.status, 200, submitted.text)
        result = submitted.json["result"]
        self.assertEqual(result["state"], "proposal-ready")
        self.assertFalse(result["verified"])
        proposal_id = result["proposalId"]
        self.assertTrue(proposal_id)

        proposals = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.project_id}/proposals",
            token=self.h.token,
        ).json["proposals"]
        self.assertEqual([row["proposalId"] for row in proposals], [proposal_id])
        digest = proposals[0]["digest"]

        # The Agent credential cannot approve its own proposal.
        denied = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.project_id}/actions/proposals/{proposal_id}/apply",
            method="POST",
            body={
                "operation": {
                    "operationId": "op_api_work_agent_apply",
                    "payload": {"action": "apply"},
                },
                "digest": digest,
            },
            capability=token,
            origin=None,
        )
        self.assertEqual(denied.status, 401, denied.text)

        # The maintainer can, and applied still is not verified.
        applied = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.project_id}/actions/proposals/{proposal_id}/apply",
            method="POST",
            body={
                "operation": {
                    "operationId": "op_api_work_maintainer_apply",
                    "payload": {"action": "apply"},
                },
                "digest": digest,
            },
            token=self.h.token,
            origin=self.h.runtime.origin,
        )
        self.assertEqual(applied.status, 200, applied.text)
        after = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.project_id}/requests/{request['requestId']}",
            token=self.h.token,
        ).json["request"]
        self.assertEqual(after["state"], "applied")
        self.assertTrue(after["applied"])
        self.assertFalse(after["verified"])

    def test_the_credential_is_scoped_to_its_project_and_request(self) -> None:
        request = self.create_request()
        self.request_action(
            "consent",
            request_id=request["requestId"],
            payload={"digest": request["contextDigest"]},
        )
        token = self.agent_token(request)
        self.claim_and_report(request)
        # Only its own request context is allowed, not the project-wide list.
        mine = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.project_id}/requests/{request['requestId']}",
            capability=token,
        )
        self.assertEqual(mine.status, 200, mine.text)
        foreign = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.other_id}/requests",
            capability=token,
        )
        self.assertEqual(foreign.status, 401)

    def test_cancel_and_retry_over_the_api(self) -> None:
        request = self.create_request()
        self.request_action(
            "consent",
            request_id=request["requestId"],
            payload={"digest": request["contextDigest"]},
        )
        token = self.agent_token(request)
        claimed = self.claim_and_report(request)
        lease = claimed["lease"]

        asked = self.request_action("cancel", request_id=request["requestId"])
        self.assertEqual(asked.status, 200, asked.text)
        self.assertEqual(asked.json["result"]["state"], "cancel-requested")
        late = self.request_action(
            "result",
            request_id=request["requestId"],
            payload={
                "attemptId": lease["attemptId"],
                "leaseId": lease["leaseId"],
                "sequence": lease["sequence"],
                "result": {"summary": "太晚了", "targetStack": "static-html",
                           "changes": []},
            },
            capability=token,
        )
        self.assertEqual(late.status, 409, late.text)

        confirmed = self.request_action(
            "confirm-cancelled", request_id=request["requestId"]
        )
        self.assertEqual(confirmed.status, 200, confirmed.text)
        self.assertEqual(confirmed.json["result"]["state"], "cancelled")
        self.assertFalse(
            (self.h.runtime.data_dir.session_dir / f"claim-{request['requestId']}.json").exists()
        )

        # Retry after a failure mints a new credential and a new attempt.
        retried_request = self.create_request(title="重试任务")
        self.request_action(
            "consent",
            request_id=retried_request["requestId"],
            payload={"digest": retried_request["contextDigest"]},
        )
        first_token = self.agent_token(retried_request)
        first_lease = self.claim_and_report(retried_request)["lease"]
        failed = self.request_action(
            "fail",
            request_id=retried_request["requestId"],
            payload={
                "attemptId": first_lease["attemptId"],
                "leaseId": first_lease["leaseId"],
                "sequence": first_lease["sequence"],
                "reason": "依赖安装被拒绝",
            },
            capability=first_token,
        )
        self.assertEqual(failed.status, 200, failed.text)
        self.assertEqual(failed.json["result"]["state"], "failed")
        retried = self.request_action("retry", request_id=retried_request["requestId"])
        self.assertEqual(retried.status, 200, retried.text)
        self.assertEqual(retried.json["result"]["state"], "waiting-for-agent")
        second_token = self.agent_token(retried_request)
        self.assertNotEqual(first_token, second_token)
        stale = self.request_action(
            "claim", request_id=retried_request["requestId"], capability=first_token
        )
        self.assertEqual(stale.status, 401)
        second_lease = self.request_action(
            "claim", request_id=retried_request["requestId"], capability=second_token
        )
        self.assertEqual(second_lease.status, 200, second_lease.text)
        self.assertEqual(second_lease.json["result"]["lease"]["sequence"], 2)


class RequestBoundCapabilityReachTest(WorkApiTestCase):
    """A request-bound capability stays on its own task; a direct proposal
    write would bypass the lease and the cancel authority (R11)."""

    def _agent_ready(self, title: str) -> tuple[dict, str]:
        request = self.create_request(title=title)
        self.request_action(
            "consent",
            request_id=request["requestId"],
            payload={"digest": request["contextDigest"]},
        )
        token = self.agent_token(request)
        self.claim_and_report(request)
        return request, token

    def test_it_reads_its_own_request_but_not_a_sibling(self) -> None:
        mine, token = self._agent_ready("我的任务")
        own = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.project_id}/requests/{mine['requestId']}",
            capability=token,
        )
        self.assertEqual(own.status, 200, own.text)
        sibling = self.create_request(title="兄弟任务")
        peek = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.project_id}/requests/{sibling['requestId']}",
            capability=token,
        )
        self.assertEqual(peek.status, 401, peek.text)

    def test_it_cannot_submit_a_proposal_directly(self) -> None:
        _, token = self._agent_ready("直写任务")
        body = {
            "operation": {
                "operationId": "op_api_r1_direct",
                "payload": {"action": "proposals"},
            },
            "changes": [
                {"path": "x.html", "operation": "create", "content": "<p/>\n"}
            ],
            "dependencyChanges": [],
        }
        denied = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.project_id}/actions/proposals",
            method="POST",
            body=body,
            capability=token,
        )
        self.assertEqual(denied.status, 401, denied.text)
        # A non-request-bound write capability still reaches the same path.
        allowed = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.project_id}/actions/proposals",
            method="POST",
            body={
                **body,
                "operation": {
                    "operationId": "op_api_r1_slash",
                    "payload": {"action": "proposals"},
                },
            },
            capability=self.capability(self.project_id, ["write"]),
        )
        self.assertEqual(allowed.status, 200, allowed.text)
    def test_a_cancelled_request_is_carried_into_the_capability_state(self) -> None:
        request, token = self._agent_ready("取消任务")
        self.request_action("cancel", request_id=request["requestId"])
        late = self.request_action(
            "heartbeat",
            request_id=request["requestId"],
            payload={"attemptId": "x", "leaseId": "y", "sequence": 1},
            capability=token,
        )
        self.assertEqual(late.status, 409, late.text)


class ProposalDependencyBindingApiTest(WorkApiTestCase):
    """The reviewed digest binds the dependency set, and an Agent result
    carries its dependencies and source request into the proposal (R11)."""

    def test_an_agent_result_carries_dependencies_and_source_request(self) -> None:
        request = self.create_request(allowedActions=["read-context", "propose-source", "add-dependency"])
        self.request_action(
            "consent",
            request_id=request["requestId"],
            payload={"digest": request["contextDigest"]},
        )
        token = self.agent_token(request)
        lease = self.claim_and_report(request)["lease"]
        deps = [{"name": "left-pad", "change": "added", "version": "1.3.0"}]
        submitted = self.request_action(
            "result",
            request_id=request["requestId"],
            payload={
                "attemptId": lease["attemptId"],
                "leaseId": lease["leaseId"],
                "sequence": lease["sequence"],
                "result": {
                    "summary": "带依赖的改动",
                    "targetStack": "static-html",
                    "changes": [
                        {"path": "index.html", "operation": "create",
                         "content": "<h1>新标题</h1>\n"}
                    ],
                    "dependencies": deps,
                    "entrypoints": {"preview": "index.html"},
                    "artifacts": [],
                },
            },
            capability=token,
        )
        self.assertEqual(submitted.status, 200, submitted.text)
        proposal_id = submitted.json["result"]["proposalId"]
        detail = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.project_id}/proposals/{proposal_id}",
            token=self.h.token,
        ).json["proposal"]
        self.assertEqual(detail["dependencyChanges"], deps)
        self.assertEqual(detail["sourceRequest"], request["requestId"])

    def test_the_digest_changes_when_only_the_dependencies_differ(self) -> None:
        def propose(operation_id: str, deps: list) -> dict:
            response = http_request(
                self.h.runtime,
                f"/api/v1/projects/{self.project_id}/actions/proposals",
                method="POST",
                body={
                    "operation": {
                        "operationId": operation_id,
                        "payload": {"action": "proposals"},
                    },
                    "changes": [
                        {"path": "dep.html", "operation": "create",
                         "content": "<p/>\n"}
                    ],
                    "dependencyChanges": deps,
                },
                token=self.h.token,
                origin=self.h.runtime.origin,
            )
            assert response.status == 200, response.text
            return response.json["result"]

        without = propose("op_api_r4_plain", [])
        with_dep = propose("op_api_r4_dep", [{"name": "left-pad", "change": "added"}])
        self.assertEqual(without["dependencyChanges"], [])
        self.assertEqual(
            with_dep["dependencyChanges"], [{"name": "left-pad", "change": "added"}]
        )
        self.assertNotEqual(without["digest"], with_dep["digest"])


if __name__ == "__main__":  # pragma: no cover - manual run
    unittest.main()
