"""Residual six-fix regressions at the real service and HTTP boundaries."""
import json

from tests import test_assets as asset_tests
from tests import test_canvas_api as canvas_api_tests
from tests import test_proposals as proposal_tests
from tests import test_work_api as work_tests
from tests.harness import http_request
from design_playbook_workbench.errors import (
    CONFLICT,
    CORRUPT_CONTENT,
    INVALID_INPUT,
    INVALID_TARGET,
    WorkbenchError,
)


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

    def test_a_conflicting_change_names_the_path_not_the_project_root(self):
        with self.assertRaises(WorkbenchError) as caught:
            self.create([{"path": "index.html", "operation": "create", "content": "x"}])
        self.assertEqual(caught.exception.code, CONFLICT)
        self.assertIn("index.html", caught.exception.detail)
        self.assertNotIn(str(self.project), caught.exception.detail)


class ImportDiagnosisTest(asset_tests.AssetTestCase):
    def test_a_refused_selection_names_only_what_the_caller_sent(self):
        # Missing and escaping selections keep one uniform rejection: the
        # detail echoes the caller's own relative input, so an operator can
        # see which selection failed without learning where anything lives.
        for selection in ("missing.md", "../escape.md"):
            with self.subTest(selection=selection):
                with self.assertRaises(WorkbenchError) as caught:
                    self.import_assets([selection])
                self.assertEqual(caught.exception.code, INVALID_TARGET)
                self.assertEqual(
                    caught.exception.detail, f"selection rejected: {selection}"
                )
                self.assertNotIn(str(self.project), caught.exception.detail)


class CanvasNameClosureTest(canvas_api_tests.CanvasApiTestCase):
    def test_canvas_name_falls_back_to_the_document(self):
        # The API create call may omit the top-level name; the name inside
        # the document then supplies it instead of a bare invalid-input.
        response = self.post("canvases", payload={"document": canvas_api_tests.CANVAS})
        self.assertEqual(response.status, 200, response.text)
        self.assertEqual(
            response.json["result"]["canvas"]["name"], canvas_api_tests.CANVAS["name"]
        )

    def test_a_canvas_with_no_name_anywhere_is_refused(self):
        response = self.post(
            "canvases", payload={"document": {**canvas_api_tests.CANVAS, "name": ""}}
        )
        self.assertEqual(response.status, 400, response.text)
        self.assertEqual(response.json["error"]["code"], INVALID_INPUT)
        self.assertIn("name", response.json["error"]["message"])
