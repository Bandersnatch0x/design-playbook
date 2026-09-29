#!/usr/bin/env python3
"""A09 over the real API: canvas routes, counters, limits, and forks.

The domain rules live in ``test_canvas.py``; these tests prove the
distributed surface is the same contract -- routes, capability scopes,
documented error codes, stale-counter conflicts, and mutation replay.
"""
from __future__ import annotations

import json
import unittest

from tests.harness import WorkbenchHarness, http_request

CANVAS = {
    "name": "首页方案",
    "boards": [
        {
            "id": "b1",
            "name": "首页",
            "width": 1200,
            "height": 800,
            "nodes": [
                {"id": "n1", "type": "stack", "children": ["n2"], "props": {},
                 "layout": {"x": 40, "y": 40, "width": 600, "height": 400, "z": 0}},
                {"id": "n2", "type": "text", "props": {"text": "标题"},
                 "layout": {"x": 60, "y": 60, "width": 320, "height": 40, "z": 1}},
            ],
            "flowEdges": [],
        }
    ],
}


class CanvasApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.h = WorkbenchHarness()
        self.addCleanup(self.h.stop)
        self.project_dir = self.h.make_directory("canvas")
        self.other_dir = self.h.make_directory("other")
        self.registered = self.h.register(self.project_dir, name="Design").json["result"]
        self.other = self.h.register(self.other_dir, name="Other").json["result"]
        self.project_id = self.registered["projectId"]
        self.other_id = self.other["projectId"]
        self.grant(self.project_id, ["read", "write"])
        self.grant(self.other_id, ["read", "write"])
        self._operations = 0

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
        canvas_id: str | None = None,
        payload: dict | None = None,
        expected: int | None = 0,
        operation_id: str | None = None,
        capability: str | None = None,
        project_id: str | None = None,
    ):
        self._operations += 1
        operation: dict = {
            "operationId": operation_id or f"op_canvas_api_{self._operations:04d}",
            "payload": {"action": verb, **(payload or {})},
        }
        if expected is not None:
            operation["expectedCounter"] = expected
        path = (
            f"/api/v1/projects/{project_id or self.project_id}/actions/canvases/"
            f"{canvas_id}/{verb}"
            if canvas_id
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

    def create(self, document: dict = CANVAS, name: str = "首页方案") -> dict:
        response = self.post("canvases", payload={"name": name, "document": document})
        assert response.status == 200, response.text
        return response.json["result"]

    def canvas_get(self, canvas_id: str, *, project_id: str | None = None, capability: str | None = None):
        return http_request(
            self.h.runtime,
            f"/api/v1/projects/{project_id or self.project_id}/canvases/{canvas_id}",
            token=None if capability else self.h.token,
            capability=capability,
        )


class CanvasApiTest(CanvasApiTestCase):
    def test_create_list_read_and_snapshot(self) -> None:
        created = self.create()
        canvas_id = created["canvas"]["canvasId"]
        self.assertEqual(created["canvas"]["counter"], 0)
        self.assertTrue(created["validation"]["valid"])

        listing = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.project_id}/canvases",
            token=self.h.token,
        )
        self.assertEqual(listing.status, 200, listing.text)
        self.assertEqual(listing.json["canvases"][0]["canvasId"], canvas_id)
        self.assertEqual(listing.json["canvases"][0]["boardCount"], 1)

        detail = self.canvas_get(canvas_id)
        self.assertEqual(detail.status, 200, detail.text)
        self.assertEqual(detail.json["document"]["boards"][0]["id"], "b1")
        self.assertEqual(detail.json["history"]["limit"], 100)
        self.assertFalse(detail.json["history"]["canUndo"])

        snapshot = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.project_id}/canvases/{canvas_id}/snapshot?boardId=b1",
            token=self.h.token,
        )
        self.assertEqual(snapshot.status, 200, snapshot.text)
        self.assertEqual(snapshot.json["previewOrigin"], self.h.preview_origin)
        self.assertTrue(snapshot.json["previewUrl"].startswith(self.h.preview_origin))
        self.assertIn("静态布局快照", snapshot.json["note"])
        extra = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.project_id}/canvases/{canvas_id}/snapshot?x=1",
            token=self.h.token,
        )
        self.assertEqual(extra.status, 400)

    def test_commands_undo_redo_and_rename_through_the_api(self) -> None:
        created = self.create()
        canvas_id = created["canvas"]["canvasId"]
        commands = [
            {"kind": "node-move", "boardId": "b1", "nodeIds": ["n2"], "dx": 10, "dy": 5},
            {"kind": "node-add", "boardId": "b1",
             "node": {"id": "n3", "type": "text", "props": {"text": "副标题"},
                      "layout": {"x": 10, "y": 10, "width": 100, "height": 30, "z": 2}}},
        ]
        applied = self.post("commands", canvas_id=canvas_id, payload={"commands": commands})
        self.assertEqual(applied.status, 200, applied.text)
        self.assertEqual(applied.json["counter"], 2)
        self.assertEqual(
            [row["sequence"] for row in applied.json["result"]["transactions"]], [1, 2]
        )
        self.assertTrue(applied.json["result"]["history"]["canUndo"])

        undone = self.post("undo", canvas_id=canvas_id, expected=2)
        self.assertEqual(undone.status, 200, undone.text)
        self.assertEqual(undone.json["result"]["stepped"]["sequence"], 2)
        self.assertNotIn(
            "n3", [node["id"] for node in undone.json["result"]["document"]["boards"][0]["nodes"]]
        )
        redone = self.post("redo", canvas_id=canvas_id, expected=3)
        self.assertEqual(redone.status, 200, redone.text)
        self.assertIn(
            "n3", [node["id"] for node in redone.json["result"]["document"]["boards"][0]["nodes"]]
        )

        renamed = self.post(
            "rename", canvas_id=canvas_id, payload={"name": "改名方案"}, expected=4
        )
        self.assertEqual(renamed.status, 200, renamed.text)
        self.assertEqual(renamed.json["result"]["canvas"]["name"], "改名方案")

    def test_counter_rules_replay_and_conflicts(self) -> None:
        created = self.create()
        canvas_id = created["canvas"]["canvasId"]
        commands = [{"kind": "node-props", "boardId": "b1", "nodeId": "n2",
                     "props": {"text": "第一次"}}]
        first = self.post(
            "commands", canvas_id=canvas_id, payload={"commands": commands},
            operation_id="op_canvas_api_replay",
        )
        self.assertEqual(first.status, 200, first.text)
        replay = self.post(
            "commands", canvas_id=canvas_id, payload={"commands": commands},
            operation_id="op_canvas_api_replay", expected=None,
        )
        self.assertEqual(replay.status, 200, replay.text)
        self.assertTrue(replay.json["replayed"])

        stale = self.post("commands", canvas_id=canvas_id, expected=0,
                          payload={"commands": commands})
        self.assertEqual(stale.status, 409, stale.text)
        self.assertEqual(stale.error_code, "conflict")

        no_counter = self.post("commands", canvas_id=canvas_id, expected=None,
                               payload={"commands": commands})
        self.assertEqual(no_counter.status, 400, no_counter.text)
        self.assertEqual(no_counter.error_code, "invalid-input")

    def test_limits_and_invalid_commands_are_refused_whole(self) -> None:
        # A real published component keeps the instance nodes resolvable, so
        # the only reason the canvas is refused is the instance ceiling.
        component = self.h.action(
            self.project_id,
            "components",
            payload={"name": "按钮", "definition": {"name": "按钮", "props": []}},
        )
        self.assertEqual(component.status, 200, component.text)
        component_id = component.json["result"]["assetId"]
        published = self.h.asset_action(
            self.project_id, component_id, "component-publish"
        )
        self.assertEqual(published.status, 200, published.text)
        nodes = [
            {"id": f"i{index}", "type": "instance",
             "props": {"assetId": component_id, "params": {}},
             "layout": {"x": 0, "y": 0, "width": 10, "height": 10, "z": index}}
            for index in range(201)
        ]
        over = {
            "name": "超量",
            "boards": [{"id": "b1", "name": "B", "width": 100, "height": 100,
                        "nodes": nodes, "flowEdges": []}],
        }
        refused = self.post("canvases", payload={"name": "超量", "document": over})
        self.assertEqual(refused.status, 413, refused.text)
        self.assertEqual(refused.error_code, "limit-exceeded")
        self.assertIn("instance-limit", refused.text)

        created = self.create()
        canvas_id = created["canvas"]["canvasId"]
        bad = self.post("commands", canvas_id=canvas_id,
                        payload={"commands": [{"kind": "nope"}]})
        self.assertEqual(bad.status, 400, bad.text)
        self.assertEqual(bad.error_code, "invalid-input")
        too_many = self.post(
            "commands", canvas_id=canvas_id,
            payload={"commands": [{"kind": "node-move", "boardId": "b1",
                                   "nodeIds": ["n2"], "dx": 1, "dy": 1}] * 21},
        )
        self.assertEqual(too_many.status, 413, too_many.text)
        self.assertEqual(
            self.canvas_get(canvas_id).json["canvas"]["counter"], 0
        )
        unknown_verb = self.post("nonsense", canvas_id=canvas_id)
        self.assertEqual(unknown_verb.status, 404)

    def test_fork_stores_a_branch_without_touching_the_original(self) -> None:
        created = self.create()
        canvas_id = created["canvas"]["canvasId"]
        draft = json.loads(json.dumps(CANVAS))
        draft["boards"][0]["nodes"][1]["layout"]["x"] = 999
        forked = self.post(
            "fork", canvas_id=canvas_id,
            payload={"name": "另一窗口", "document": draft},
        )
        self.assertEqual(forked.status, 200, forked.text)
        result = forked.json["result"]
        self.assertEqual(result["forkedFrom"], canvas_id)
        self.assertEqual(result["canvas"]["name"], "另一窗口")
        original = self.canvas_get(canvas_id).json
        self.assertEqual(
            next(n for n in original["document"]["boards"][0]["nodes"]
                 if n["id"] == "n2")["layout"]["x"],
            60,
        )

    def test_foreign_and_unknown_canvases_are_refused(self) -> None:
        created = self.create()
        canvas_id = created["canvas"]["canvasId"]
        foreign = self.canvas_get(canvas_id, project_id=self.other_id)
        self.assertEqual(foreign.status, 400)
        self.assertEqual(foreign.error_code, "invalid-target")
        ghost = self.canvas_get("00000000-0000-4000-8000-000000000000")
        self.assertEqual(ghost.status, 400)
        self.assertEqual(ghost.error_code, "invalid-target")


class CanvasCapabilityTest(CanvasApiTestCase):
    def test_a_read_capability_cannot_command_a_canvas(self) -> None:
        created = self.create()
        canvas_id = created["canvas"]["canvasId"]
        read_only = self.capability(self.project_id, ["read"])
        readable = self.canvas_get(canvas_id, capability=read_only)
        self.assertEqual(readable.status, 200, readable.text)
        denied = self.post(
            "commands", canvas_id=canvas_id,
            payload={"commands": [{"kind": "node-move", "boardId": "b1",
                                   "nodeIds": ["n2"], "dx": 1, "dy": 1}]},
            capability=read_only,
        )
        self.assertEqual(denied.status, 401, denied.text)
        denied_create = self.post(
            "canvases", payload={"name": "X", "document": CANVAS}, capability=read_only
        )
        self.assertEqual(denied_create.status, 401)
        denied_undo = self.post("undo", canvas_id=canvas_id, capability=read_only)
        self.assertEqual(denied_undo.status, 401)

    def test_a_capability_is_scoped_to_its_own_project(self) -> None:
        created = self.create()
        canvas_id = created["canvas"]["canvasId"]
        write_other = self.capability(self.other_id, ["read", "write"])
        response = self.canvas_get(canvas_id, capability=write_other)
        self.assertEqual(response.status, 401)


if __name__ == "__main__":  # pragma: no cover - manual run
    unittest.main()
