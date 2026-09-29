"""Residual six-fix regressions at the real service and HTTP boundaries."""
import json

from tests import test_assets as asset_tests
from tests import test_proposals as proposal_tests
from tests import test_work_api as work_tests
from tests.harness import http_request
from design_playbook_workbench.errors import CONFLICT, CORRUPT_CONTENT, WorkbenchError


class ReplayClosureTest(asset_tests.AssetTestCase):
    def test_replay_is_bound_to_project_as_well_as_asset(self):
        self.write("brand.md", "# Brand\n")
        asset = self.import_assets(["brand.md"])["asset"]["assetId"]
        self.grant(["read", "write"])
        op = self.operation({"action": "publish", "assetId": asset})
        self.assets.publish_revision(self.project_id, asset, operation=op)
        with self.assertRaises(WorkbenchError) as caught:
            self.assets.publish_revision("another-project", asset, operation=op)
        self.assertEqual(caught.exception.code, CONFLICT)


class RequestClosureTest(work_tests.WorkApiTestCase):
    def ready(self, actions=None):
        request = self.create_request(**({"allowedActions": actions} if actions else {}))
        self.request_action("consent", request_id=request["requestId"], payload={"digest": request["contextDigest"]})
        lease = self.claim_and_report(request)["lease"]
        return request, self.agent_token(request), lease

    def test_task_cannot_read_unselected_project_data(self):
        _, token, _ = self.ready()
        for suffix in ("", "/assets", "/requests", "/canvases"):
            with self.subTest(suffix=suffix):
                response = http_request(self.h.runtime, f"/api/v1/projects/{self.project_id}{suffix}", capability=token)
                self.assertEqual(response.status, 401, response.text)

    def test_cancelled_task_cannot_read_context(self):
        request, token, _ = self.ready()
        self.request_action("cancel", request_id=request["requestId"])
        response = http_request(self.h.runtime, f"/api/v1/projects/{self.project_id}/requests/{request['requestId']}", capability=token)
        self.assertEqual(response.status, 409, response.text)

    def test_result_cannot_exceed_granted_actions(self):
        request, token, lease = self.ready(["read-context"])
        response = self.request_action("result", request_id=request["requestId"], capability=token,
            payload={"attemptId": lease["attemptId"], "leaseId": lease["leaseId"], "sequence": lease["sequence"],
                "result": {"summary": "not granted", "targetStack": "static-html", "changes": [{"path": "forbidden.html", "operation": "create", "content": "no"}], "artifacts": []}})
        self.assertEqual(response.status, 401, response.text)
        self.assertEqual(self.h.runtime.store.project_proposals(self.project_id), [])

    def test_replay_binds_actual_http_body_not_client_digest_claim(self):
        body = {"operation": {"operationId": "op_replay_actual_body", "payload": {}},
                "changes": [{"path": "draft.html", "operation": "create", "content": "one"}]}
        def send():
            return http_request(self.h.runtime, f"/api/v1/projects/{self.project_id}/actions/proposals", method="POST", body=body, token=self.h.token, origin=self.h.runtime.origin)
        first = send()
        self.assertEqual(first.status, 200, first.text)
        self.assertTrue(send().json["replayed"])
        body["changes"][0]["content"] = "different"
        response = send()
        self.assertEqual(response.status, 409, response.text)


class ProposalClosureTest(proposal_tests.ProposalTestCase):
    def test_dependency_metadata_cannot_change_under_approved_digest(self):
        proposal = self.create([{"path": "new.html", "operation": "create", "content": "hello"}])
        row = self.store.proposal(proposal["proposalId"])
        payload = json.loads(row["payload_json"])
        payload["dependencyChanges"] = [{"name": "unreviewed", "change": "added"}]
        with self.store.transaction():
            self.store.connection.execute("UPDATE proposals SET payload_json = ? WHERE proposal_id = ?", (json.dumps(payload), proposal["proposalId"]))
        with self.assertRaises(WorkbenchError) as caught:
            self.apply(proposal)
        self.assertIn(caught.exception.code, (CONFLICT, CORRUPT_CONTENT))
        self.assertFalse((self.project / "new.html").exists())
