#!/usr/bin/env python3
"""R11: the slash side claims a task with its OS-protected credential.

The workbench mints a private per-request credential at consent; this proves
the client that reads it can claim the task over the same typed API, and that
it refuses honestly when there is nothing to claim with.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = REPO_ROOT / "packages" / "design-playbook"
WORKBENCH_DIR = REPO_ROOT / "packages" / "design-playbook-workbench"
for candidate in (PLUGIN_DIR, WORKBENCH_DIR):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from design_playbook.scripts import workbench_claim  # noqa: E402

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


def _load_workbench_harness():
    """Load the workbench test harness by path, never by package name.

    `tests` is a regular package in two plugin directories, so importing it by
    name can bind the other one. The workbench harness is loaded from its own
    file for the same reason ``test_project_target`` does it.
    """
    harness_path = WORKBENCH_DIR / "tests" / "harness.py"
    spec = importlib.util.spec_from_file_location("wb_harness_for_claim", harness_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


HARNESS = _load_workbench_harness()


class WorkbenchClaimTest(unittest.TestCase):
    def setUp(self) -> None:
        self.h = HARNESS.WorkbenchHarness()
        self.addCleanup(self.h.stop)
        self.data_dir = self.h.runtime.data_dir.root
        self.project_dir = self.h.make_directory("claim")
        registered = self.h.register(self.project_dir, name="Design").json["result"]
        self.project_id = registered["projectId"]
        self.grant()
        self.canvas_id = self._create_canvas()
        self.selection = self._confirm_context()

    def grant(self) -> None:
        counter = self.h.project_target(self.project_id)["counter"]
        assert (
            self.h.grant(self.project_id, ["read", "write"], expected_counter=counter).status
            == 200
        )

    def _post(self, path: str, body: dict):
        return HARNESS.http_request(
            self.h.runtime,
            path,
            method="POST",
            body=body,
            token=self.h.token,
            origin=self.h.runtime.origin,
        )

    def _create_canvas(self) -> str:
        created = self._post(
            f"/api/v1/projects/{self.project_id}/actions/canvases",
            {
                "operation": {"operationId": "op_claim_canvas",
                              "payload": {"action": "canvases"}},
                "name": "任务画布",
                "document": CANVAS,
            },
        )
        assert created.status == 200, created.text
        return created.json["result"]["canvas"]["canvasId"]

    def _confirm_context(self) -> dict:
        built = self._post(
            f"/api/v1/projects/{self.project_id}/actions/canvases/"
            f"{self.canvas_id}/contexts",
            {
                "operation": {"operationId": "op_claim_context",
                              "payload": {"action": "contexts"}},
                "boardId": "b1",
                "nodeIds": ["n2"],
            },
        )
        assert built.status == 200, built.text
        selection = built.json["result"]
        confirmed = self._post(
            f"/api/v1/projects/{self.project_id}/actions/canvases/"
            f"{self.canvas_id}/confirm",
            {
                "operation": {"operationId": "op_claim_confirm",
                              "payload": {"action": "confirm"}},
                "selectionId": selection["selectionId"],
                "digest": selection["digest"],
            },
        )
        assert confirmed.status == 200, confirmed.text
        return confirmed.json["result"]

    def _create_request(self) -> dict:
        created = self._post(
            f"/api/v1/projects/{self.project_id}/actions/requests",
            {
                "operation": {"operationId": "op_claim_request",
                              "payload": {"action": "requests"}},
                "title": "首页静态改版",
                "goal": "把首页标题改成新文案",
                "targetStack": "static-html",
                "contextSelectionId": self.selection["selectionId"],
                "expiresInSeconds": 3600,
                "plan": {"reuse": [], "adapt": [], "new": ["标题"]},
                "allowedActions": ["read-context", "propose-source"],
                "resultSchema": {"required": ["summary"]},
            },
        )
        assert created.status == 200, created.text
        return created.json["result"]

    def _consent(self, request: dict) -> dict:
        consented = self._post(
            f"/api/v1/projects/{self.project_id}/actions/requests/"
            f"{request['requestId']}/consent",
            {
                "operation": {"operationId": "op_claim_consent",
                              "payload": {"action": "consent"}},
                "digest": request["contextDigest"],
            },
        )
        assert consented.status == 200, consented.text
        return consented.json["result"]

    def test_claiming_without_a_record_refuses_and_says_why(self) -> None:
        request = self._create_request()
        with self.assertRaises(workbench_claim.ClaimError) as caught:
            workbench_claim.claim_request(
                request_id=request["requestId"], data_dir=self.data_dir
            )
        self.assertIn("confirm the send scope", str(caught.exception))

    def test_the_client_claims_the_task_with_the_private_credential(self) -> None:
        request = self._create_request()
        self._consent(request)
        # The credential is on disk, readable by this OS user only, and is
        # never returned by the service in a payload.
        record_path = workbench_claim.claim_record_path(
            self.data_dir, request["requestId"]
        )
        self.assertTrue(record_path.is_file())
        record = json.loads(record_path.read_text(encoding="utf-8"))
        self.assertEqual(record["projectId"], self.project_id)

        payload = workbench_claim.claim_request(
            request_id=request["requestId"], data_dir=self.data_dir
        )
        lease = payload["result"]["lease"]
        self.assertEqual(lease["sequence"], 1)
        self.assertTrue(lease["attemptId"])
        self.assertTrue(lease["leaseId"])
        self.assertEqual(lease["heartbeatSeconds"], 15)
        self.assertEqual(payload["result"]["state"], "running")
        # The token stayed in the record: no response echoes it.
        self.assertNotIn(record["token"], json.dumps(payload))

        # A second claim of the same request is a conflict, not a second lease.
        with self.assertRaises(workbench_claim.ClaimError):
            workbench_claim.claim_request(
                request_id=request["requestId"], data_dir=self.data_dir
            )


if __name__ == "__main__":  # pragma: no cover - manual run
    unittest.main()
