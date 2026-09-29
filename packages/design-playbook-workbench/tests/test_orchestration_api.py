#!/usr/bin/env python3
"""A10 over the real API: scheme snapshots, comparison, and context routes.

The domain rules live in ``test_orchestration.py``; these tests prove the
distributed surface: the routes exist, capability scopes hold, error codes
are the documented ones, and the serialized selection a caller receives is
the one that would be sent.
"""
from __future__ import annotations

import json
import unittest

from tests.harness import WorkbenchHarness, http_request

CANVAS = {
    "name": "方案画布",
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
        },
        {
            "id": "b2",
            "name": "详情",
            "width": 1200,
            "height": 800,
            "nodes": [
                {"id": "p2", "type": "text", "children": [], "props": {"text": "详情"},
                 "layout": {"x": 40, "y": 40, "width": 200, "height": 40, "z": 0}},
            ],
            "flowEdges": [],
            "scheme": None,
        },
    ],
}


class OrchestrationApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.h = WorkbenchHarness()
        self.addCleanup(self.h.stop)
        self._operations = 0
        self.project_dir = self.h.make_directory("orchestration")
        self.other_dir = self.h.make_directory("other")
        self.registered = self.h.register(self.project_dir, name="Design").json["result"]
        self.other = self.h.register(self.other_dir, name="Other").json["result"]
        self.project_id = self.registered["projectId"]
        self.other_id = self.other["projectId"]
        self.grant(self.project_id, ["read", "write"])
        self.grant(self.other_id, ["read", "write"])
        created = self.post(
            "canvases", payload={"name": "方案画布", "document": CANVAS}
        )
        assert created.status == 200, created.text
        self.canvas_id = created.json["result"]["canvas"]["canvasId"]

    def grant(self, project_id: str, scopes: list[str]) -> None:
        counter = self.h.project_target(project_id)["counter"]
        assert self.h.grant(project_id, scopes, expected_counter=counter).status == 200

    def capability(self, project_id: str, scopes: list[str]) -> str:
        return self.h.runtime.session.issue_capability(
            project_id=project_id, scopes=scopes
        )

    def post(
        self,
        verb: str,
        *,
        payload: dict | None = None,
        expected: int | None = 0,
        canvas_id: str | None = None,
        project_id: str | None = None,
        operation_id: str | None = None,
        capability: str | None = None,
    ):
        self._operations += 1
        operation: dict = {
            "operationId": operation_id or f"op_orch_api_{self._operations:04d}",
            "payload": {"action": verb, **(payload or {})},
        }
        if expected is not None:
            operation["expectedCounter"] = expected
        canvas = canvas_id if canvas_id is not None else getattr(self, "canvas_id", None)
        path = (
            f"/api/v1/projects/{project_id or self.project_id}/actions/canvases/"
            f"{canvas}/{verb}"
            if canvas
            else f"/api/v1/projects/{project_id or self.project_id}/actions/canvases"
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

    def get(self, suffix: str, *, capability: str | None = None):
        return http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.project_id}/canvases/{self.canvas_id}/{suffix}",
            token=None if capability else self.h.token,
            capability=capability,
        )

    def commands(self, commands: list[dict], *, expected: int):
        return self.post("commands", payload={"commands": commands}, expected=expected)


class FlowAndSchemeApiTest(OrchestrationApiTestCase):
    def test_flow_edges_and_scheme_metadata_over_the_api(self) -> None:
        response = self.commands(
            [
                {"kind": "flow-edge-add", "boardId": "b1",
                 "edge": {"id": "f1", "from": "n2", "to": "b2", "kind": "navigation",
                          "label": "去详情"}},
                {"kind": "flow-edge-add", "boardId": "b2",
                 "edge": {"id": "f2", "from": "p2", "to": "b1"}},
                {"kind": "board-scheme", "boardId": "b1",
                 "scheme": {"viewport": {"width": 1440, "height": 900, "device": "desktop"},
                            "rules": ["8pt 间距"], "replaceableRegions": ["n2"],
                            "acceptance": "首屏可到达详情"}},
            ],
            expected=0,
        )
        self.assertEqual(response.status, 200, response.text)
        self.assertEqual(response.json["counter"], 3)
        self.assertTrue(response.json["result"]["validation"]["valid"])
        document = response.json["result"]["document"]
        home = document["boards"][0]
        self.assertEqual([edge["id"] for edge in home["flowEdges"]], ["f1"])
        self.assertEqual(home["scheme"]["viewport"]["width"], 1440)

        derived = self.commands(
            [{"kind": "scheme-derive", "boardId": "b1", "newBoardId": "b3", "name": "方案 B"}],
            expected=3,
        )
        self.assertEqual(derived.status, 200, derived.text)
        boards = derived.json["result"]["document"]["boards"]
        self.assertEqual([board["id"] for board in boards], ["b1", "b2", "b3"])
        self.assertEqual(
            next(board for board in boards if board["id"] == "b3")["scheme"]["derivedFrom"]["boardId"],
            "b1",
        )

        invalid = self.commands(
            [{"kind": "flow-edge-add", "boardId": "b1",
              "edge": {"id": "f9", "from": "ghost", "to": "n2"}}],
            expected=4,
        )
        self.assertEqual(invalid.status, 400, invalid.text)
        self.assertEqual(invalid.error_code, "invalid-input")


class SnapshotApiTest(OrchestrationApiTestCase):
    def test_snapshots_list_read_and_compare(self) -> None:
        first = self.post("snapshots", payload={"boardId": "b1", "note": "基线"}, expected=0)
        self.assertEqual(first.status, 200, first.text)
        self.assertTrue(first.json["result"]["frozen"])
        snapshot_id = first.json["result"]["snapshotId"]

        listing = self.get("snapshots")
        self.assertEqual(listing.status, 200, listing.text)
        self.assertEqual([row["snapshotId"] for row in listing.json["snapshots"]], [snapshot_id])
        detail = self.get(f"snapshots/{snapshot_id}")
        self.assertEqual(detail.status, 200, detail.text)
        self.assertEqual(detail.json["snapshot"]["note"], "基线")
        self.assertEqual(detail.json["snapshot"]["nodeCount"], 2)
        missing = self.get("snapshots/00000000-0000-4000-8000-000000000000")
        self.assertEqual(missing.status, 400)
        self.assertEqual(missing.error_code, "invalid-target")

        second = self.post(
            "snapshots", payload={"boardId": "b2", "note": "B"}, expected=1
        )
        self.assertEqual(second.status, 200, second.text)
        compared = self.post(
            "compare",
            payload={"left": snapshot_id, "right": second.json["result"]["snapshotId"]},
            expected=1,
        )
        self.assertEqual(compared.status, 200, compared.text)
        result = compared.json["result"]
        self.assertIsNone(result["winner"])
        self.assertIsNone(result["approval"])
        self.assertIn("不选择赢家", result["note"])
        self.assertFalse(result["differences"]["sameContent"])
        self.assertEqual(result["differences"]["nodeCount"], {"left": 2, "right": 1})
        refused = self.post(
            "compare", payload={"left": snapshot_id, "right": snapshot_id}, expected=1
        )
        self.assertEqual(refused.status, 400)

    def test_a_frozen_snapshot_keeps_its_hash_after_canvas_edits(self) -> None:
        frozen = self.post("snapshots", payload={"boardId": "b1"}, expected=0)
        self.assertEqual(frozen.status, 200, frozen.text)
        hash_before = frozen.json["result"]["contentHash"]
        edited = self.commands(
            [{"kind": "node-props", "boardId": "b1", "nodeId": "n2",
              "props": {"text": "改过的标题"}}],
            expected=0,
        )
        self.assertEqual(edited.status, 200, edited.text)
        after = self.get(f"snapshots/{frozen.json['result']['snapshotId']}")
        self.assertEqual(after.json["snapshot"]["contentHash"], hash_before)
        self.assertEqual(after.json["snapshot"]["counter"], 0)


class ContextApiTest(OrchestrationApiTestCase):
    def build(self, payload: dict, *, expected: int = 0, operation_id: str | None = None):
        return self.post(
            "contexts", payload=payload, expected=expected, operation_id=operation_id
        )

    def test_a_selection_serializes_exactly_what_would_be_sent(self) -> None:
        (self.project_dir / "notes.md").write_bytes(b"notes\n")
        (self.project_dir / ".env").write_bytes(b"TOKEN=secret\n")
        response = self.build(
            {"boardId": "b1", "nodeIds": ["n2"], "filePaths": ["notes.md"]}
        )
        self.assertEqual(response.status, 200, response.text)
        selection = response.json["result"]
        self.assertEqual(selection["state"], "draft")
        self.assertEqual([node["nodeId"] for node in selection["nodes"]], ["n2"])
        self.assertEqual(selection["files"][0]["path"], "notes.md")
        self.assertEqual(selection["files"][0]["size"], 6)
        self.assertTrue(selection["digest"].startswith("sha256:"))
        kinds = {row["kind"] for row in selection["exclusions"]}
        self.assertIn("credentials", kinds)
        self.assertIn("run-and-evidence-logs", kinds)
        self.assertEqual(
            selection["totals"]["bytes"],
            selection["totals"]["nodeBytes"]
            + selection["totals"]["revisionBytes"]
            + selection["totals"]["fileBytes"],
        )
        self.assertNotIn("TOKEN", json.dumps(selection))

        credential = self.build({"boardId": "b1", "nodeIds": ["n2"], "filePaths": [".env"]})
        self.assertEqual(credential.status, 400, credential.text)
        self.assertEqual(credential.error_code, "invalid-input")
        self.assertNotIn("TOKEN", credential.text)

        listing = self.get("contexts")
        self.assertEqual(listing.status, 200, listing.text)
        self.assertEqual(len(listing.json["selections"]), 1)
        detail = self.get(f"contexts/{selection['selectionId']}")
        self.assertEqual(detail.status, 200, detail.text)
        self.assertEqual(detail.json["selection"]["digest"], selection["digest"])

    def test_confirm_binds_the_digest_and_a_change_invalidates_it(self) -> None:
        created = self.build({"boardId": "b1", "nodeIds": ["n2"]})
        selection = created.json["result"]
        confirmed = self.post(
            "confirm",
            payload={"selectionId": selection["selectionId"], "digest": selection["digest"]},
        )
        self.assertEqual(confirmed.status, 200, confirmed.text)
        self.assertEqual(confirmed.json["result"]["state"], "confirmed")

        stale = self.post(
            "confirm",
            payload={"selectionId": selection["selectionId"], "digest": "sha256:" + "0" * 64},
        )
        self.assertEqual(stale.status, 409, stale.text)
        self.assertEqual(stale.error_code, "conflict")

        changed = self.build(
            {"selectionId": selection["selectionId"], "boardId": "b1", "nodeIds": ["n2", "n1"]}
        )
        self.assertEqual(changed.status, 200, changed.text)
        self.assertEqual(changed.json["result"]["state"], "draft")
        self.assertTrue(changed.json["result"]["staleConfirmation"])
        self.assertEqual(
            changed.json["result"]["confirmed"]["digest"], selection["digest"]
        )
        again = self.post(
            "confirm",
            payload={"selectionId": selection["selectionId"], "digest": selection["digest"]},
        )
        self.assertEqual(again.status, 409)

    def test_replay_and_unknown_content(self) -> None:
        payload = {"boardId": "b1", "nodeIds": ["n2"]}
        first = self.build(payload, operation_id="op_orch_api_replay")
        self.assertEqual(first.status, 200, first.text)
        replay = self.build(payload, expected=None, operation_id="op_orch_api_replay")
        self.assertEqual(replay.status, 200, replay.text)
        self.assertTrue(replay.json["replayed"])
        unknown = self.build({"boardId": "b1", "nodeIds": ["ghost"]})
        self.assertEqual(unknown.status, 400)
        self.assertEqual(unknown.error_code, "invalid-target")
        empty = self.build({"boardId": "b1", "nodeIds": []})
        self.assertEqual(empty.status, 400)
        missing_selection = self.post(
            "confirm", payload={"selectionId": "00000000-0000-4000-8000-000000000000",
                                "digest": "sha256:" + "0" * 64}
        )
        self.assertEqual(missing_selection.status, 400)


class OrchestrationCapabilityTest(OrchestrationApiTestCase):
    def test_a_capability_can_read_but_never_change(self) -> None:
        read_only = self.capability(self.project_id, ["read"])
        write_cap = self.capability(self.project_id, ["read", "write"])
        # Snapshots/contexts are the maintainer's orchestration workspace;
        # only the browser session creates them. An Agent capability never
        # holds maintainer authoring rights, even with project write scope
        # (R10/R11).
        created = self.post("snapshots", payload={"boardId": "b1"})
        self.assertEqual(created.status, 200, created.text)
        listing = self.get("snapshots", capability=read_only)
        self.assertEqual(listing.status, 200, listing.text)
        denied_read = self.post(
            "snapshots", payload={"boardId": "b1"}, capability=read_only
        )
        self.assertEqual(denied_read.status, 401)
        denied_write = self.post(
            "snapshots", payload={"boardId": "b1"}, capability=write_cap
        )
        self.assertEqual(denied_write.status, 401)
        denied_context = self.post(
            "contexts", payload={"boardId": "b1", "nodeIds": ["n2"]},
            capability=write_cap,
        )
        self.assertEqual(denied_context.status, 401)
        write_other = self.capability(self.other_id, ["read", "write"])
        foreign = self.get("snapshots", capability=write_other)
        self.assertEqual(foreign.status, 401)

    def test_foreign_projects_and_unknown_verbs_are_refused(self) -> None:
        created = self.post("snapshots", payload={"boardId": "b1"})
        snapshot_id = created.json["result"]["snapshotId"]
        foreign = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.other_id}/canvases/{self.canvas_id}"
            f"/snapshots/{snapshot_id}",
            token=self.h.token,
        )
        self.assertEqual(foreign.status, 400)
        self.assertEqual(foreign.error_code, "invalid-target")
        unknown = self.post("nonsense")
        self.assertEqual(unknown.status, 404)


if __name__ == "__main__":  # pragma: no cover - manual run
    unittest.main()
