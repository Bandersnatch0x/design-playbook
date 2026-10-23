#!/usr/bin/env python3
"""R11: the slash side claims a task with its OS-protected credential.

The workbench mints a private per-request credential at consent; this proves
the client that reads it can claim the task over the same typed API, and that
it refuses honestly when there is nothing to claim with.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
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


class WorkbenchClaimTestCase(unittest.TestCase):
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


class WorkbenchClaimTest(WorkbenchClaimTestCase):
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


class WorkbenchTaskTest(WorkbenchClaimTestCase):
    def ready(self) -> tuple[dict, dict]:
        request = self._create_request()
        self._consent(request)
        claimed = workbench_claim.claim_request(
            request_id=request["requestId"], data_dir=self.data_dir
        )
        return request, claimed["result"]["lease"]

    def cli(self, action: str, request_id: str, *extra: str, stdin: bytes | None = None):
        return subprocess.run(
            [sys.executable, str(PLUGIN_DIR / "scripts" / "workbench_task.py"),
             action, "--request", request_id, "--data-dir", str(self.data_dir), *extra],
            input=stdin,
            capture_output=True,
            timeout=20,
            env={**os.environ, "PYTHONIOENCODING": "cp1252"},
        )

    @staticmethod
    def lease_args(lease: dict) -> list[str]:
        return ["--attempt-id", lease["attemptId"], "--lease-id", lease["leaseId"],
                "--sequence", str(lease["sequence"])]

    def test_read_heartbeat_result_and_maintainer_approval(self) -> None:
        request, lease = self.ready()
        rid = request["requestId"]
        read = self.cli("read", rid)
        self.assertEqual(read.returncode, 0, read.stderr)
        detail = json.loads(read.stdout.decode("utf-8"))["request"]
        for field in ("context", "plan", "allowedActions", "resultSchema"):
            self.assertTrue(detail[field])
        self.assertEqual(detail["goal"], request["goal"])
        beat = self.cli("heartbeat", rid, *self.lease_args(lease),
                        "--stage", "完成标题", "--count", "1", "--operation-id", "task-beat")
        self.assertEqual(beat.returncode, 0, beat.stderr)
        conflicting = self.cli("heartbeat", rid, *self.lease_args(lease),
                               "--stage", "完成标题", "--count", "2", "--operation-id", "task-beat")
        self.assertEqual(conflicting.returncode, 1)
        self.assertIn(b"conflict", conflicting.stderr)
        after = self.cli("read", rid)
        progress = json.loads(after.stdout.decode("utf-8"))["request"]["attempt"]["progress"]
        self.assertEqual(progress, {"stage": "完成标题", "count": 1})
        result = {"summary": "改写标题", "changes": [
            {"path": "index.html", "operation": "create", "content": "<h1>新标题</h1>"}
        ]}
        submitted = self.cli("result", rid, *self.lease_args(lease), "--result", "-",
                             stdin=json.dumps(result, ensure_ascii=False).encode("utf-8"))
        self.assertEqual(submitted.returncode, 0, submitted.stderr)
        payload = json.loads(submitted.stdout.decode("utf-8"))["result"]
        self.assertEqual(payload["state"], "proposal-ready")
        self.assertFalse(payload["verified"])
        self.assertFalse((self.project_dir / "index.html").exists())
        proposal = self.h.proposal_detail(self.project_id, payload["proposalId"]).json["proposal"]
        record = workbench_claim.read_claim_record(self.data_dir, rid)
        denied = self.h.proposal_action(
            self.project_id, payload["proposalId"], "apply",
            digest=proposal["digest"], capability=record["token"],
        )
        self.assertEqual(denied.status, 401, denied.text)
        applied = self.h.proposal_action(
            self.project_id, payload["proposalId"], "apply", digest=proposal["digest"]
        )
        self.assertEqual(applied.status, 200, applied.text)
        self.assertEqual((self.project_dir / "index.html").read_text(encoding="utf-8"),
                         "<h1>新标题</h1>")
        for output in (read.stdout, beat.stdout, submitted.stdout, submitted.stderr):
            self.assertNotIn(record["token"].encode(), output)

    def test_failure_reports_the_observed_reason(self) -> None:
        request, lease = self.ready()
        failed = self.cli("fail", request["requestId"], *self.lease_args(lease),
                          "--reason", "构建失败", "--operation-id", "task-fail")
        self.assertEqual(failed.returncode, 0, failed.stderr)
        result = json.loads(failed.stdout.decode("utf-8"))["result"]
        self.assertEqual(result["state"], "failed")
        self.assertEqual(result["attempt"]["progress"]["note"], "构建失败")

    def test_result_file_and_service_schema_refusal(self) -> None:
        request, lease = self.ready()
        path = self.h.base / "result.json"
        path.write_text('{"notes": "缺少 summary"}', encoding="utf-8")
        args = (*self.lease_args(lease), "--result", str(path), "--operation-id", "task-result")
        refused = self.cli("result", request["requestId"], *args)
        self.assertEqual(refused.returncode, 1)
        self.assertIn("result is missing: summary", refused.stderr.decode("utf-8"))
        path.write_text('{"summary": "完成"}', encoding="utf-8")
        accepted = self.cli("result", request["requestId"], *args)
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        replayed = self.cli("result", request["requestId"], *args)
        self.assertEqual(replayed.returncode, 0, replayed.stderr)
        self.assertTrue(json.loads(replayed.stdout)["replayed"])

    def test_stale_lease_and_missing_claim_refuse(self) -> None:
        missing = self.cli("read", "missing-request")
        self.assertEqual(missing.returncode, 1)
        self.assertIn(b"confirm the send scope", missing.stderr)
        request, lease = self.ready()
        stale = {**lease, "sequence": lease["sequence"] + 1}
        refused = self.cli("heartbeat", request["requestId"], *self.lease_args(stale),
                           "--stage", "editing", "--count", "1")
        self.assertEqual(refused.returncode, 1)
        self.assertIn(b"conflict", refused.stderr)

    def test_request_read_cannot_use_another_requests_credential(self) -> None:
        request, _ = self.ready()
        rid = request["requestId"]
        record = workbench_claim.read_claim_record(self.data_dir, rid)
        foreign_id = "00000000-0000-4000-8000-000000000000"
        foreign = {**record, "requestId": foreign_id}
        workbench_claim.claim_record_path(self.data_dir, foreign_id).write_text(
            json.dumps(foreign), encoding="utf-8"
        )
        denied = self.cli("read", foreign_id)
        self.assertEqual(denied.returncode, 1)
        self.assertIn(b"unauthorized", denied.stderr)
        self.assertNotIn(record["token"].encode(), denied.stderr)
        workbench_claim.claim_record_path(self.data_dir, rid).write_text(
            json.dumps(foreign), encoding="utf-8"
        )
        mismatched = self.cli("read", rid)
        self.assertEqual(mismatched.returncode, 1)
        self.assertIn(b"different request", mismatched.stderr)

    def test_invalid_reports_are_rejected_before_sending(self) -> None:
        request, lease = self.ready()
        rid = request["requestId"]
        for action, extra in (
            ("heartbeat", ["--stage", "editing", "--count", "-1"]),
            ("heartbeat", ["--count", "0"]),
            ("fail", ["--reason", " "]),
            ("result", []),
        ):
            with self.subTest(action=action, extra=extra):
                invalid = self.cli(action, rid, *self.lease_args(lease), *extra)
                self.assertEqual(invalid.returncode, 2, invalid.stderr)
        for raw in (b"{", b"[]", b"\xff"):
            with self.subTest(raw=raw):
                invalid = self.cli("result", rid, *self.lease_args(lease),
                                   "--result", "-", stdin=raw)
                self.assertEqual(invalid.returncode, 1, invalid.stderr)
        missing_lease = self.cli("fail", rid, "--reason", "failed")
        self.assertEqual(missing_lease.returncode, 2)


if __name__ == "__main__":  # pragma: no cover - manual run
    unittest.main()
