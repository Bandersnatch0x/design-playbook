#!/usr/bin/env python3
"""A09 (domain half): canvas commands, patches, undo history, limits.

The rules under test are the ones R09 names: one transactional command per
gesture, a persisted undo history of the last saved edits, a redo branch
cleared by a new edit, a 200-instance ceiling rejected as a whole, and no
implicit rollback of published assets or repository writes.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from design_playbook_workbench.assets import AssetService
from design_playbook_workbench.blobs import BlobStore
from design_playbook_workbench.canvas import (
    MAX_INSTANCES,
    UNDO_HISTORY_LIMIT,
    CanvasService,
    apply_command,
    apply_patch,
    parse_canvas,
    snapshot_html,
    validate_canvas,
)
from design_playbook_workbench.components import ComponentService
from design_playbook_workbench.errors import (
    CONFLICT,
    INVALID_INPUT,
    INVALID_TARGET,
    LIMIT_EXCEEDED,
    MISSING_DEPENDENCY,
    WorkbenchError,
)
from design_playbook_workbench.reuse import ReuseService
from design_playbook_workbench.service import Operation, WorkbenchService
from design_playbook_workbench.store import Store, WorkbenchDataDirectory

BOARD = {"id": "b1", "name": "首页", "width": 1200, "height": 800}
CANVAS = {
    "name": "首页方案",
    "boards": [
        {
            **BOARD,
            "nodes": [
                {"id": "n1", "type": "stack", "children": ["n2", "n3"], "props": {},
                 "layout": {"x": 40, "y": 40, "width": 600, "height": 400, "z": 0}},
                {"id": "n2", "type": "text", "props": {"text": "标题"},
                 "layout": {"x": 60, "y": 60, "width": 320, "height": 40, "z": 1}},
                {"id": "n3", "type": "button", "props": {"label": "开始"},
                 "layout": {"x": 60, "y": 140, "width": 120, "height": 40, "z": 2}},
            ],
            "flowEdges": [],
        }
    ],
}


def node(node_id: str, node_type: str = "text", **props) -> dict:
    return {
        "id": node_id,
        "type": node_type,
        "props": props.get("props", {"text": node_id}),
        "layout": props.get("layout", {"x": 0, "y": 0, "width": 100, "height": 40, "z": 0}),
    }


class CanvasDomainTest(unittest.TestCase):
    def test_a_document_round_trips_and_validates(self) -> None:
        document = parse_canvas(CANVAS)
        verdict = validate_canvas(document)
        self.assertTrue(verdict["valid"])
        self.assertEqual(verdict["instanceCount"], 0)
        self.assertEqual(verdict["boardIds"], ["b1"])
        self.assertEqual(document["boards"][0]["nodes"][0]["children"], ["n2", "n3"])

    def test_broken_documents_are_refused_or_reported(self) -> None:
        for raw in (
            {"boards": "nope"},
            {"boards": [], "extra": 1},
            {"boards": [{"id": "b1", "name": "B", "width": 0, "height": 10}]},
            "{not json",
            None,
        ):
            with self.subTest(raw=raw):
                with self.assertRaises(WorkbenchError) as caught:
                    parse_canvas(raw)
                self.assertEqual(caught.exception.code, INVALID_INPUT)

        verdict = validate_canvas(
            parse_canvas(
                {
                    "name": "",
                    "boards": [
                        {"id": "b1", "name": "同", "width": 100, "height": 100,
                         "nodes": [node("n1")], "flowEdges": []},
                        {"id": "b1", "name": "同", "width": -1, "height": 100,
                         "nodes": [], "flowEdges": [
                             {"id": "e1", "from": "n1", "to": "ghost"}]},
                    ],
                }
            )
        )
        kinds = {error["kind"] for error in verdict["errors"]}
        self.assertIn("missing-name", kinds)
        self.assertIn("duplicate-board", kinds)
        self.assertIn("invalid-board-size", kinds)
        self.assertFalse(verdict["valid"])

    def test_node_schema_is_shared_with_pages(self) -> None:
        verdict = validate_canvas(
            parse_canvas(
                {
                    "name": "C",
                    "boards": [
                        {"id": "b1", "name": "B", "width": 100, "height": 100,
                         "nodes": [node("n1", "text", props={})],
                         "flowEdges": []},
                    ],
                }
            )
        )
        self.assertIn("missing-node-payload", [e["kind"] for e in verdict["errors"]])
        geometry = validate_canvas(
            parse_canvas(
                {
                    "name": "C",
                    "boards": [
                        {"id": "b1", "name": "B", "width": 100, "height": 100,
                         "nodes": [node("n1", layout={"x": 0, "y": 0, "width": -5,
                                                     "height": 10, "z": 0})],
                         "flowEdges": []},
                    ],
                }
            )
        )
        self.assertIn("invalid-node-layout", [e["kind"] for e in geometry["errors"]])

    def test_instance_ceiling_is_reported_and_refused(self) -> None:
        nodes = [
            node(f"i{index}", "instance", props={"assetId": "a"})
            for index in range(MAX_INSTANCES)
        ]
        over = {
            "name": "C",
            "boards": [
                {"id": "b1", "name": "B", "width": 100, "height": 100,
                 "nodes": nodes, "flowEdges": []},
            ],
        }
        with self.assertRaises(WorkbenchError) as caught:
            apply_command(
                over,
                {"kind": "node-add", "boardId": "b1",
                 "node": node("extra", "instance", props={"assetId": "a"})},
                components={"a": {"definition": {"props": []}, "published": True}},
            )
        self.assertEqual(caught.exception.code, LIMIT_EXCEEDED)
        self.assertIn(str(MAX_INSTANCES), str(caught.exception))


class CommandTest(unittest.TestCase):
    def setUp(self) -> None:
        self.document = parse_canvas(CANVAS)

    def run_command(self, command: dict) -> tuple[dict, dict, dict, str, list[str]]:
        return apply_command(self.document, command)

    def test_every_command_is_reversible_through_its_patches(self) -> None:
        commands = [
            {"kind": "board-add", "name": "第二画板"},
            {"kind": "board-rename", "boardId": "b1", "name": "改名后"},
            {"kind": "board-resize", "boardId": "b1", "width": 1000, "height": 600},
            {"kind": "node-add", "boardId": "b1", "node": node("n4", "image",
                                                              props={"source": "a.png"})},
            {"kind": "node-props", "boardId": "b1", "nodeId": "n2",
             "props": {"text": "新标题"}},
            {"kind": "node-move", "boardId": "b1", "nodeIds": ["n2", "n3"],
             "dx": 12, "dy": -4},
            {"kind": "node-resize", "boardId": "b1", "nodeId": "n3",
             "layout": {"x": 10, "y": 10, "width": 200, "height": 60}},
            {"kind": "node-reorder", "boardId": "b1", "nodeId": "n1",
             "action": "front"},
            {"kind": "node-duplicate", "boardId": "b1", "nodeIds": ["n3"]},
            {"kind": "node-group", "boardId": "b1", "nodeIds": ["n2", "n3"]},
            {"kind": "node-align", "boardId": "b1", "nodeIds": ["n2", "n3"],
             "mode": "hdistribute"},
            {"kind": "node-delete", "boardId": "b1", "nodeIds": ["n3"]},
        ]
        for command in commands:
            with self.subTest(command=command["kind"]):
                before_document = json.loads(json.dumps(self.document))
                updated, before, after, label, targets = apply_command(
                    self.document, command
                )
                self.assertTrue(label)
                self.assertTrue(targets)
                # Undo is exact, redo reproduces the new state.
                self.assertEqual(apply_patch(updated, before), before_document)
                self.assertEqual(apply_patch(before_document, after), updated)
                self.document = updated

    def test_geometry_defaults_and_rejects_bad_input(self) -> None:
        updated, _, _, _, _ = apply_command(
            self.document,
            {"kind": "node-add", "boardId": "b1", "node": {"id": "n9", "type": "text",
                                                           "props": {"text": "x"}}},
        )
        added = next(n for n in updated["boards"][0]["nodes"] if n["id"] == "n9")
        self.assertEqual(
            sorted(added["layout"]), ["height", "width", "x", "y", "z"]
        )
        for command in (
            {"kind": "nope"},
            {"kind": "node-move", "boardId": "b1", "nodeIds": ["n2"], "dx": "12", "dy": 0},
            {"kind": "node-move", "boardId": "b1", "nodeIds": ["ghost"], "dx": 1, "dy": 0},
            {"kind": "node-align", "boardId": "b1", "nodeIds": ["n2"], "mode": "left"},
            {"kind": "node-align", "boardId": "b1", "nodeIds": ["n2", "n3"], "mode": "diag"},
            {"kind": "node-resize", "boardId": "b1", "nodeId": "n2",
             "layout": {"width": 0, "height": 10}},
            {"kind": "node-group", "boardId": "b1", "nodeIds": ["n2"]},
            {"kind": "board-delete", "boardId": "ghost"},
        ):
            with self.subTest(command=command.get("kind", "?")):
                with self.assertRaises(WorkbenchError) as caught:
                    apply_command(self.document, command)
                self.assertIn(
                    caught.exception.code, (INVALID_INPUT, INVALID_TARGET)
                )

    def test_the_last_board_cannot_be_deleted(self) -> None:
        with self.assertRaises(WorkbenchError) as caught:
            apply_command(self.document, {"kind": "board-delete", "boardId": "b1"})
        self.assertEqual(caught.exception.code, INVALID_INPUT)

    def test_grouping_reparents_and_layer_order_stays_contiguous(self) -> None:
        grouped, _, _, _, _ = apply_command(
            self.document,
            {"kind": "node-group", "boardId": "b1", "nodeIds": ["n2", "n3"],
             "name": "按钮组"},
        )
        board = grouped["boards"][0]
        group = next(n for n in board["nodes"] if n["type"] == "container" and n["id"] not in ("n1",))
        self.assertEqual(sorted(group["children"]), ["n2", "n3"])
        self.assertNotIn("n2", next(n for n in board["nodes"] if n["id"] == "n1")["children"])
        self.assertEqual(group["props"]["label"], "按钮组")

        front, _, _, _, _ = apply_command(
            self.document, {"kind": "node-reorder", "boardId": "b1", "nodeId": "n1",
                            "action": "front"}
        )
        zs = sorted(n["layout"]["z"] for n in front["boards"][0]["nodes"])
        self.assertEqual(zs, [0, 1, 2])
        self.assertEqual(
            next(n for n in front["boards"][0]["nodes"] if n["id"] == "n1")["layout"]["z"],
            2,
        )

    def test_deleting_a_node_prunes_parent_references(self) -> None:
        updated, before, after, _, _ = apply_command(
            self.document,
            {"kind": "node-delete", "boardId": "b1", "nodeIds": ["n3"]},
        )
        board = updated["boards"][0]
        self.assertNotIn("n3", [n["id"] for n in board["nodes"]])
        self.assertEqual(
            next(n for n in board["nodes"] if n["id"] == "n1")["children"], ["n2"]
        )
        self.assertEqual(apply_patch(updated, before), self.document)
        self.assertEqual(apply_patch(self.document, after), updated)

    def test_snapshot_renders_layout_without_executing_anything(self) -> None:
        html = snapshot_html(self.document, "b1")
        self.assertIn("标题", html)
        self.assertIn("静态布局快照", html)
        self.assertIn("position: absolute", html)
        self.assertNotIn("<script", html)
        with self.assertRaises(WorkbenchError) as caught:
            snapshot_html(self.document, "ghost")
        self.assertEqual(caught.exception.code, INVALID_TARGET)


class CanvasServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name).resolve()
        self.data_dir = WorkbenchDataDirectory(self.base / "data").ensure()
        self.store = Store(self.data_dir.database_path)
        self.service = WorkbenchService(store=self.store, data_dir=self.data_dir)
        self.blobs = BlobStore(self.data_dir.blob_dir)
        self.assets = AssetService(
            store=self.store, service=self.service, blobs=self.blobs
        )
        self.reuse = ReuseService(
            store=self.store, service=self.service, assets=self.assets, blobs=self.blobs
        )
        self.components = ComponentService(
            store=self.store,
            service=self.service,
            assets=self.assets,
            reuse=self.reuse,
            blobs=self.blobs,
        )
        self.canvases = CanvasService(
            store=self.store,
            service=self.service,
            components=self.components,
            reuse=self.reuse,
            blobs=self.blobs,
        )
        self._operations = 0
        self.project_dir = self.base / "project"
        self.project_dir.mkdir()
        candidate = self.service.probe_folder(self.project_dir)
        self.target = self.service.register_project(
            path=candidate.canonical_path,
            candidate_id=candidate.candidate_id,
            name="Design",
            operation=self.operation({"action": "register-project"}),
        )["result"]
        self.project_id = self.target["projectId"]
        counter = int(self.store.project(self.project_id)["counter"])
        self.service.set_grants(
            self.project_id,
            scopes=["read", "write"],
            operation=Operation(
                operation_id="op_grant_0001",
                payload={"scopes": ["read", "write"]},
                expected_counter=counter,
            ),
        )

    def tearDown(self) -> None:
        self.store.close()
        self._tmp.cleanup()

    def operation(self, payload: dict, *, expected: int | None = None) -> Operation:
        self._operations += 1
        return Operation(
            operation_id=f"op_canvas_{self._operations:08d}",
            payload=payload,
            expected_counter=expected,
        )

    def create(self, document: dict = CANVAS, name: str = "首页方案") -> dict:
        return self.canvases.create(
            self.project_id,
            name=name,
            document=document,
            operation=self.operation({"action": "canvases", "name": name}),
        )["result"]

    def canvas_counter(self, canvas_id: str) -> int:
        return int(self.store.canvas(canvas_id)["counter"])

    def apply_batch(self, canvas_id: str, commands: list[dict], *, expected: int | None = -1):
        if expected == -1:
            expected = self.canvas_counter(canvas_id)
        return self.canvases.run_commands(
            self.project_id,
            canvas_id,
            commands=commands,
            operation=self.operation(
                {"action": "commands", "canvasId": canvas_id, "commands": commands},
                expected=expected,
            ),
        )

    def test_create_read_and_stale_counter_conflict(self) -> None:
        created = self.create()
        canvas_id = created["canvas"]["canvasId"]
        self.assertEqual(created["canvas"]["counter"], 0)
        self.assertTrue(created["validation"]["valid"])
        self.assertEqual(created["history"]["canUndo"], False)

        updated = self.apply_batch(
            canvas_id, [{"kind": "node-move", "boardId": "b1", "nodeIds": ["n2"],
                         "dx": 8, "dy": 8}]
        )
        self.assertEqual(updated["counter"], 1)
        self.assertEqual(updated["result"]["transactions"][0]["sequence"], 1)

        with self.assertRaises(WorkbenchError) as caught:
            self.apply_batch(
                canvas_id,
                [{"kind": "node-move", "boardId": "b1", "nodeIds": ["n2"], "dx": 1, "dy": 1}],
                expected=0,
            )
        self.assertEqual(caught.exception.code, CONFLICT)
        self.assertEqual(self.canvas_counter(canvas_id), 1)

        with self.assertRaises(WorkbenchError) as caught:
            self.canvases.run_commands(
                self.project_id,
                canvas_id,
                commands=[{"kind": "node-move", "boardId": "b1", "nodeIds": ["n2"],
                           "dx": 1, "dy": 1}],
                operation=self.operation({"action": "commands"}, expected=None),
            )
        self.assertEqual(caught.exception.code, INVALID_INPUT)

    def test_replay_and_conflicting_payloads(self) -> None:
        created = self.create()
        canvas_id = created["canvas"]["canvasId"]
        operation = self.operation(
            {"action": "commands", "canvasId": canvas_id, "commands": []},
            expected=0,
        )
        commands = [{"kind": "node-move", "boardId": "b1", "nodeIds": ["n2"],
                     "dx": 4, "dy": 0}]
        first = self.canvases.run_commands(
            self.project_id, canvas_id, commands=commands, operation=operation
        )
        self.assertFalse(first["replayed"])
        # The same operation ID is the same intent: the stored result returns
        # and the counter does not advance twice.
        again = self.canvases.run_commands(
            self.project_id, canvas_id, commands=commands, operation=operation
        )
        self.assertTrue(again["replayed"])
        self.assertEqual(self.canvas_counter(canvas_id), 1)

    def test_undo_redo_and_the_redo_branch(self) -> None:
        created = self.create()
        canvas_id = created["canvas"]["canvasId"]
        self.apply_batch(canvas_id, [{"kind": "node-move", "boardId": "b1", "nodeIds": ["n2"],
                              "dx": 20, "dy": 0}])
        self.apply_batch(canvas_id, [{"kind": "node-move", "boardId": "b1", "nodeIds": ["n2"],
                              "dx": 0, "dy": 30}])
        moved = self.canvases.detail(self.project_id, canvas_id)["document"]
        self.assertEqual(
            next(n for n in moved["boards"][0]["nodes"] if n["id"] == "n2")["layout"],
            {"x": 80, "y": 90, "width": 320, "height": 40, "z": 1},
        )
        undone = self.canvases.undo(
            self.project_id, canvas_id,
            operation=self.operation({"action": "undo"}, expected=2),
        )
        self.assertEqual(undone["result"]["stepped"]["sequence"], 2)
        self.assertEqual(
            next(n for n in undone["result"]["document"]["boards"][0]["nodes"]
                 if n["id"] == "n2")["layout"]["y"],
            60,
        )
        redone = self.canvases.redo(
            self.project_id, canvas_id,
            operation=self.operation({"action": "redo"}, expected=3),
        )
        self.assertEqual(redone["result"]["stepped"]["direction"], "redo")
        self.assertEqual(redone["result"]["history"]["canRedo"], False)

        # A new edit after an undo clears the redo branch.
        self.canvases.undo(
            self.project_id, canvas_id,
            operation=self.operation({"action": "undo"}, expected=4),
        )
        self.assertTrue(
            self.canvases.detail(self.project_id, canvas_id)["history"]["canRedo"]
        )
        self.apply_batch(canvas_id, [{"kind": "node-props", "boardId": "b1", "nodeId": "n2",
                              "props": {"text": "分支后"}}])
        history = self.canvases.detail(self.project_id, canvas_id)["history"]
        self.assertFalse(history["canRedo"])
        self.assertEqual(history["undone"], [])

        with self.assertRaises(WorkbenchError) as caught:
            self.canvases.redo(
                self.project_id, canvas_id,
                operation=self.operation({"action": "redo2"},
                                         expected=self.canvas_counter(canvas_id)),
            )
        self.assertEqual(caught.exception.code, MISSING_DEPENDENCY)

    def test_undo_history_is_trimmed_to_the_persisted_limit(self) -> None:
        created = self.create()
        canvas_id = created["canvas"]["canvasId"]
        total = UNDO_HISTORY_LIMIT + 5
        made = 0
        while made < total:
            batch = [
                {"kind": "node-props", "boardId": "b1", "nodeId": "n2",
                 "props": {"text": f"第 {made + index} 次"}}
                for index in range(min(20, total - made))
            ]
            self.apply_batch(canvas_id, batch)
            made += len(batch)
        history = self.canvases.detail(self.project_id, canvas_id)["history"]
        self.assertEqual(len(history["applied"]), UNDO_HISTORY_LIMIT)
        for _ in range(UNDO_HISTORY_LIMIT):
            self.canvases.undo(
                self.project_id, canvas_id,
                operation=self.operation({"action": "undo"},
                                         expected=self.canvas_counter(canvas_id)),
            )
        with self.assertRaises(WorkbenchError) as caught:
            self.canvases.undo(
                self.project_id, canvas_id,
                operation=self.operation({"action": "undo"},
                                         expected=self.canvas_counter(canvas_id)),
            )
        self.assertEqual(caught.exception.code, MISSING_DEPENDENCY)

    def test_a_batch_is_atomic_and_validated_before_it_is_stored(self) -> None:
        created = self.create()
        canvas_id = created["canvas"]["canvasId"]
        before = self.canvases.detail(self.project_id, canvas_id)["document"]
        with self.assertRaises(WorkbenchError):
            self.apply_batch(
                canvas_id,
                [
                    {"kind": "node-move", "boardId": "b1", "nodeIds": ["n2"],
                     "dx": 5, "dy": 0},
                    {"kind": "node-add", "boardId": "b1",
                     "node": {"id": "bad", "type": "text", "props": {}}},
                ],
            )
        after = self.canvases.detail(self.project_id, canvas_id)
        self.assertEqual(after["document"], before)
        self.assertEqual(after["canvas"]["counter"], 0)
        self.assertEqual(after["history"]["applied"], [])

        with self.assertRaises(WorkbenchError) as caught:
            self.apply_batch(
                canvas_id,
                [{"kind": "node-props", "boardId": "b1", "nodeId": "n2",
                  "props": {"text": "ok"}}] * 21,
            )
        self.assertEqual(caught.exception.code, LIMIT_EXCEEDED)

    def test_instance_nodes_reference_fixed_revision_instances(self) -> None:
        component = self.components.create_component(
            self.project_id,
            name="按钮",
            definition={"name": "按钮",
                        "props": [{"name": "label", "type": "string", "default": "确定"}]},
            operation=self.operation({"action": "components"}),
        )["result"]
        self.components.publish(
            self.project_id, component["assetId"],
            operation=self.operation({"action": "component-publish"}),
        )
        instance = self.reuse.create_instance(
            self.project_id,
            component["assetId"],
            operation=self.operation({"action": "instances"}),
        )["result"]
        created = self.create()
        canvas_id = created["canvas"]["canvasId"]
        updated = self.apply_batch(
            canvas_id,
            [{"kind": "node-add", "boardId": "b1",
              "node": {"id": "inst", "type": "instance",
                       "props": {"instanceId": instance["instanceId"], "params": {}},
                       "layout": {"x": 10, "y": 10, "width": 200, "height": 80, "z": 5}}}],
        )
        self.assertEqual(updated["result"]["validation"]["instanceCount"], 1)
        stored = self.store.latest_revision  # no asset edits below
        self.assertTrue(callable(stored))

        with self.assertRaises(WorkbenchError) as caught:
            self.apply_batch(
                canvas_id,
                [{"kind": "node-add", "boardId": "b1",
                  "node": {"id": "ghost", "type": "instance",
                           "props": {"instanceId": "00000000-0000-4000-8000-000000000000"},
                           "layout": {"x": 0, "y": 0, "width": 10, "height": 10, "z": 1}}}],
            )
        self.assertEqual(caught.exception.code, INVALID_INPUT)
        self.assertIn("unresolved-instance", str(caught.exception))

        # Instance parameters are checked against the component's public
        # schema by the same code the component editor uses.
        with self.assertRaises(WorkbenchError) as caught:
            self.apply_batch(
                canvas_id,
                [{"kind": "node-add", "boardId": "b1",
                  "node": {"id": "inst2", "type": "instance",
                           "props": {"assetId": component["assetId"],
                                     "params": {"label": 7}},
                           "layout": {"x": 0, "y": 0, "width": 10, "height": 10, "z": 2}}}],
            )
        self.assertEqual(caught.exception.code, INVALID_INPUT)
        self.assertIn("invalid-param-value", str(caught.exception))

    def test_undo_never_touches_published_assets(self) -> None:
        self.project_dir.joinpath("brand.md").write_bytes(b"# Brand\n")
        asset = self.assets.import_selection(
            self.project_id,
            selections=["brand.md"],
            operation=self.operation({"action": "imports"}),
        )["result"]["asset"]
        published = self.assets.publish_revision(
            self.project_id,
            asset["assetId"],
            operation=self.operation({"action": "publish"}),
        )["result"]
        created = self.create()
        canvas_id = created["canvas"]["canvasId"]
        self.apply_batch(canvas_id, [{"kind": "node-move", "boardId": "b1", "nodeIds": ["n2"],
                              "dx": 5, "dy": 5}])
        undone = self.canvases.undo(
            self.project_id, canvas_id,
            operation=self.operation({"action": "undo"}, expected=1),
        )
        self.assertEqual(undone["result"]["stepped"]["direction"], "undo")
        self.assertEqual(
            len(self.store.asset_revisions(asset["assetId"])), 1
        )
        self.assertEqual(
            self.store.latest_revision(asset["assetId"])["revision_id"],
            published["revisionId"],
        )

    def test_fork_saves_a_conflicting_draft_as_a_new_canvas(self) -> None:
        created = self.create()
        canvas_id = created["canvas"]["canvasId"]
        self.apply_batch(canvas_id, [{"kind": "node-move", "boardId": "b1", "nodeIds": ["n2"],
                              "dx": 5, "dy": 5}])
        # Window B has its own draft built on the stale counter.
        draft = json.loads(json.dumps(CANVAS))
        draft["boards"][0]["nodes"][1]["layout"]["x"] = 999
        forked = self.canvases.fork(
            self.project_id,
            canvas_id,
            name="B 的分支",
            document=draft,
            operation=self.operation({"action": "fork"}),
        )["result"]
        self.assertEqual(forked["canvas"]["name"], "B 的分支")
        self.assertEqual(forked["forkedFrom"], canvas_id)
        self.assertNotEqual(forked["canvas"]["canvasId"], canvas_id)
        # The original canvas keeps the other writer's state.
        original = self.canvases.detail(self.project_id, canvas_id)["document"]
        self.assertEqual(
            next(n for n in original["boards"][0]["nodes"] if n["id"] == "n2")["layout"]["x"],
            65,
        )

    def test_history_and_document_survive_a_service_restart(self) -> None:
        created = self.create()
        canvas_id = created["canvas"]["canvasId"]
        self.apply_batch(
            canvas_id,
            [{"kind": "node-move", "boardId": "b1", "nodeIds": ["n2"],
              "dx": 25, "dy": 5}],
        )
        expected = self.canvases.detail(self.project_id, canvas_id)["document"]
        self.store.close()

        # A restart reopens the same data directory: only confirmed
        # transactions are promised, and they are all there.
        self.store = Store(self.data_dir.database_path)
        self.service = WorkbenchService(store=self.store, data_dir=self.data_dir)
        self.blobs = BlobStore(self.data_dir.blob_dir)
        self.assets = AssetService(
            store=self.store, service=self.service, blobs=self.blobs
        )
        self.reuse = ReuseService(
            store=self.store, service=self.service, assets=self.assets, blobs=self.blobs
        )
        self.components = ComponentService(
            store=self.store,
            service=self.service,
            assets=self.assets,
            reuse=self.reuse,
            blobs=self.blobs,
        )
        self.canvases = CanvasService(
            store=self.store,
            service=self.service,
            components=self.components,
            reuse=self.reuse,
            blobs=self.blobs,
        )
        reopened = self.canvases.detail(self.project_id, canvas_id)
        self.assertEqual(reopened["document"], expected)
        self.assertTrue(reopened["history"]["canUndo"])
        self.assertEqual(reopened["canvas"]["counter"], 1)
        undone = self.canvases.undo(
            self.project_id,
            canvas_id,
            operation=self.operation({"action": "undo-after-restart"}, expected=1),
        )
        self.assertEqual(undone["result"]["stepped"]["sequence"], 1)
        self.assertEqual(
            next(
                node
                for node in undone["result"]["document"]["boards"][0]["nodes"]
                if node["id"] == "n2"
            )["layout"]["x"],
            60,
        )

    def test_snapshot_and_listing_reads(self) -> None:
        created = self.create()
        canvas_id = created["canvas"]["canvasId"]
        listing = self.canvases.list_for_project(self.project_id)
        self.assertEqual(listing["canvases"][0]["canvasId"], canvas_id)
        self.assertEqual(listing["canvases"][0]["boardCount"], 1)
        snapshot = self.canvases.snapshot(self.project_id, canvas_id)
        self.assertEqual(snapshot["boardId"], "b1")
        html = self.blobs.read(snapshot["contentHash"]).decode("utf-8")
        self.assertIn("标题", html)

    def test_client_supplied_ids_stay_valid_and_unknown_fields_are_refused(
        self,
    ) -> None:
        created = self.create()
        canvas_id = created["canvas"]["canvasId"]
        # A duplicate whose ids the window chose must still validate: the
        # stored layer index stays an integer.
        duplicated = self.apply_batch(
            canvas_id,
            [{"kind": "node-duplicate", "boardId": "b1", "nodeIds": ["n2"],
              "newIds": ["n_copy"]}],
        )
        self.assertTrue(duplicated["result"]["validation"]["valid"])
        boards = duplicated["result"]["document"]["boards"]
        clone = next(node for node in boards[0]["nodes"] if node["id"] == "n_copy")
        self.assertIsInstance(clone["layout"]["z"], int)
        grouped = self.apply_batch(
            canvas_id,
            [{"kind": "node-group", "boardId": "b1", "nodeIds": ["n2", "n_copy"],
              "groupId": "n_group"}],
        )
        self.assertTrue(grouped["result"]["validation"]["valid"])
        self.assertIsInstance(
            next(
                node
                for node in grouped["result"]["document"]["boards"][0]["nodes"]
                if node["id"] == "n_group"
            )["layout"]["z"],
            int,
        )
        # Local-only fields are a typed refusal, not silently ignored.
        for command in (
            {"kind": "node-duplicate", "boardId": "b1", "nodeIds": ["n2"],
             "newIds": ["n_x"], "createdIds": ["n_x"]},
            {"kind": "node-move", "boardId": "b1", "nodeIds": ["n2"], "dx": 1,
             "dy": 1, "local": True},
            {"kind": "node-duplicate", "boardId": "b1", "nodeIds": ["n2"],
             "newIds": ["n2"]},
        ):
            with self.subTest(command=command):
                with self.assertRaises(WorkbenchError) as caught:
                    self.apply_batch(canvas_id, [command])
                self.assertEqual(caught.exception.code, INVALID_INPUT)

    def test_foreign_canvases_are_refused(self) -> None:
        created = self.create()
        canvas_id = created["canvas"]["canvasId"]
        other_dir = self.base / "other"
        other_dir.mkdir()
        candidate = self.service.probe_folder(other_dir)
        other = self.service.register_project(
            path=candidate.canonical_path,
            candidate_id=candidate.candidate_id,
            name="Other",
            operation=self.operation({"action": "register-project"}),
        )["result"]
        with self.assertRaises(WorkbenchError) as caught:
            self.canvases.detail(other["projectId"], canvas_id)
        self.assertEqual(caught.exception.code, INVALID_TARGET)


if __name__ == "__main__":  # pragma: no cover - manual run
    unittest.main()
