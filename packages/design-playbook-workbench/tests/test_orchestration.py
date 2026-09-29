#!/usr/bin/env python3
"""A10: flow edges, scheme constraints, fixed snapshots, context selections.

The rules under test are the ones R10 names: navigation may loop while asset
lineage stays untouched, comparison works from frozen snapshots and crowns
no winner, and a context carries exactly what was selected -- with a digest
that a confirmation is bound to.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from design_playbook_workbench.assets import AssetService
from design_playbook_workbench.blobs import BlobStore
from design_playbook_workbench.canvas import CanvasService, parse_canvas, validate_canvas
from design_playbook_workbench.components import ComponentService
from design_playbook_workbench.errors import (
    CONFLICT,
    INVALID_INPUT,
    INVALID_TARGET,
    LIMIT_EXCEEDED,
    WorkbenchError,
)
from design_playbook_workbench.orchestration import OrchestrationService
from design_playbook_workbench.reuse import ReuseService
from design_playbook_workbench.service import Operation, WorkbenchService
from design_playbook_workbench.store import Store, WorkbenchDataDirectory

CANVAS = {
    "name": "方案画布",
    "boards": [
        {
            "id": "b1",
            "name": "首页",
            "width": 1200,
            "height": 800,
            "nodes": [
                {"id": "n1", "type": "stack", "children": ["n2", "n3"], "props": {},
                 "layout": {"x": 40, "y": 40, "width": 600, "height": 400, "z": 0}},
                {"id": "n2", "type": "text", "children": [], "props": {"text": "标题"},
                 "layout": {"x": 60, "y": 60, "width": 320, "height": 40, "z": 1}},
                {"id": "n3", "type": "button", "children": [], "props": {"label": "开始"},
                 "layout": {"x": 60, "y": 140, "width": 120, "height": 40, "z": 2}},
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


class OrchestrationTestCase(unittest.TestCase):
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
        self.orchestration = OrchestrationService(
            store=self.store,
            service=self.service,
            canvases=self.canvases,
            assets=self.assets,
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
                operation_id="op_grant_orch",
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
            operation_id=f"op_orch_{self._operations:08d}",
            payload=payload,
            expected_counter=expected,
        )

    # -- helpers ---------------------------------------------------------

    def create_canvas(self, document: dict = CANVAS) -> dict:
        return self.canvases.create(
            self.project_id,
            name="方案画布",
            document=document,
            operation=self.operation({"action": "canvases"}),
        )["result"]

    def canvas_counter(self, canvas_id: str) -> int:
        return int(self.store.canvas(canvas_id)["counter"])

    def apply_batch(self, canvas_id: str, commands: list[dict]) -> dict:
        return self.canvases.run_commands(
            self.project_id,
            canvas_id,
            commands=commands,
            operation=self.operation(
                {"action": "commands", "canvasId": canvas_id, "commands": commands},
                expected=self.canvas_counter(canvas_id),
            ),
        )["result"]

    def board(self, canvas_id: str, board_id: str = "b1") -> dict:
        document = self.canvases.detail(self.project_id, canvas_id)["document"]
        return next(item for item in document["boards"] if item["id"] == board_id)

    def publish_markdown(self, name: str = "brand.md", body: bytes = b"# Brand\n") -> dict:
        (self.project_dir / name).write_bytes(body)
        asset = self.assets.import_selection(
            self.project_id,
            selections=[name],
            operation=self.operation({"action": "imports"}),
        )["result"]["asset"]
        self.assets.publish_revision(
            self.project_id,
            asset["assetId"],
            operation=self.operation({"action": "publish"}),
        )
        return asset


class FlowEdgeTest(OrchestrationTestCase):
    def test_navigation_edges_may_loop_and_never_touch_asset_lineage(self) -> None:
        created = self.create_canvas()
        canvas_id = created["canvas"]["canvasId"]
        lineage_before = self.store.lineage("n1")
        result = self.apply_batch(
            canvas_id,
            [
                {"kind": "flow-edge-add", "boardId": "b1",
                 "edge": {"id": "f1", "from": "n3", "to": "b2", "kind": "navigation",
                          "label": "前往详情"}},
                {"kind": "flow-edge-add", "boardId": "b1",
                 "edge": {"id": "f2", "from": "n2", "to": "n3"}},
                {"kind": "flow-edge-add", "boardId": "b2",
                 "edge": {"id": "f3", "from": "p2", "to": "b1"}},
                # A loop back into the same board is a normal user flow.
                {"kind": "flow-edge-add", "boardId": "b2",
                 "edge": {"id": "f4", "from": "p2", "to": "p2"}},
            ],
        )
        self.assertTrue(result["validation"]["valid"])
        edges = self.board(canvas_id, "b2")["flowEdges"]
        self.assertEqual([edge["id"] for edge in edges], ["f3", "f4"])
        self.assertEqual(result["validation"]["boardIds"], ["b1", "b2"])
        # Navigation is not lineage: nothing here writes a derived-from edge.
        self.assertEqual(self.store.lineage("n1"), lineage_before)
        self.assertEqual(self.store.dependencies("n1"), [])

        updated = self.apply_batch(
            canvas_id,
            [{"kind": "flow-edge-update", "boardId": "b1", "edgeId": "f2",
              "edge": {"kind": "user-flow", "label": "主流程"}}],
        )
        edge = next(
            item for item in updated["document"]["boards"][0]["flowEdges"] if item["id"] == "f2"
        )
        self.assertEqual(edge["kind"], "user-flow")
        self.assertEqual(edge["label"], "主流程")

        deleted = self.apply_batch(
            canvas_id,
            [{"kind": "flow-edge-delete", "boardId": "b1", "edgeId": "f2"}],
        )
        self.assertEqual(
            [item["id"] for item in deleted["document"]["boards"][0]["flowEdges"]], ["f1"]
        )

    def test_endpoints_must_exist_and_kinds_are_closed(self) -> None:
        created = self.create_canvas()
        canvas_id = created["canvas"]["canvasId"]
        for command in (
            {"kind": "flow-edge-add", "boardId": "b1",
             "edge": {"id": "f1", "from": "ghost", "to": "n2"}},
            {"kind": "flow-edge-add", "boardId": "b1",
             "edge": {"id": "f2", "from": "n2", "to": "n3", "kind": "teleport"}},
            {"kind": "flow-edge-add", "boardId": "b1", "edge": {"id": "f3", "from": "n2"}},
            {"kind": "flow-edge-add", "boardId": "b1",
             "edge": {"id": "f4", "from": "n2", "to": "n3", "extra": 1}},
        ):
            with self.subTest(command=command["edge"].get("id")):
                with self.assertRaises(WorkbenchError) as caught:
                    self.apply_batch(canvas_id, [command])
                self.assertEqual(caught.exception.code, INVALID_INPUT)
        # An endpoint that exists only as another board's node is refused.
        with self.assertRaises(WorkbenchError) as caught:
            self.apply_batch(
                canvas_id,
                [{"kind": "flow-edge-add", "boardId": "b1",
                  "edge": {"id": "f5", "from": "n2", "to": "p2"}}],
            )
        self.assertEqual(caught.exception.code, INVALID_INPUT)

    def test_flow_edges_survive_undo_and_redo_through_the_board_patch(self) -> None:
        created = self.create_canvas()
        canvas_id = created["canvas"]["canvasId"]
        self.apply_batch(
            canvas_id,
            [{"kind": "flow-edge-add", "boardId": "b1",
              "edge": {"id": "f1", "from": "n2", "to": "n3"}}],
        )
        undone = self.canvases.undo(
            self.project_id, canvas_id,
            operation=self.operation({"action": "undo"}, expected=self.canvas_counter(canvas_id)),
        )["result"]
        self.assertEqual(undone["document"]["boards"][0]["flowEdges"], [])
        redone = self.canvases.redo(
            self.project_id, canvas_id,
            operation=self.operation({"action": "redo"}, expected=self.canvas_counter(canvas_id)),
        )["result"]
        self.assertEqual(
            [edge["id"] for edge in redone["document"]["boards"][0]["flowEdges"]], ["f1"]
        )


class SchemeTest(OrchestrationTestCase):
    def test_scheme_constraints_round_trip_and_are_validated(self) -> None:
        created = self.create_canvas()
        canvas_id = created["canvas"]["canvasId"]
        scheme = {
            "viewport": {"width": 1440, "height": 900, "device": "desktop"},
            "rules": ["使用 8pt 间距", "主色仅用于主操作"],
            "replaceableRegions": ["n3"],
            "acceptance": "首页首屏在主操作上完成一次点击即可到达详情。",
        }
        result = self.apply_batch(canvas_id, [{"kind": "board-scheme", "boardId": "b1", "scheme": scheme}])
        self.assertTrue(result["validation"]["valid"])
        stored = self.board(canvas_id)["scheme"]
        self.assertEqual(stored["viewport"]["width"], 1440)
        self.assertEqual(stored["replaceableRegions"], ["n3"])

        for bad in (
            {"viewport": {"width": 0, "height": 900}},
            {"viewport": {"width": 1440, "height": 900}, "replaceableRegions": ["ghost"]},
            {"viewport": {"width": 1440, "height": 900}, "rules": ["x" * 300]},
            {"viewport": {"width": 1440, "height": 900}, "rules": ["r"] * 21},
            {"viewport": {"width": 1440, "height": 900}, "unknown": 1},
        ):
            with self.subTest(bad=sorted(bad)):
                with self.assertRaises(WorkbenchError) as caught:
                    self.apply_batch(canvas_id, [{"kind": "board-scheme", "boardId": "b1", "scheme": bad}])
                self.assertIn(
                    caught.exception.code, (INVALID_INPUT, LIMIT_EXCEEDED)
                )

    def test_a_derived_scheme_is_its_own_document_with_lineage(self) -> None:
        created = self.create_canvas()
        canvas_id = created["canvas"]["canvasId"]
        self.apply_batch(
            canvas_id,
            [
                {"kind": "board-scheme", "boardId": "b1",
                 "scheme": {"viewport": {"width": 1440, "height": 900},
                            "replaceableRegions": ["n3"], "rules": ["规则"], "acceptance": "验收"}},
                {"kind": "flow-edge-add", "boardId": "b1",
                 "edge": {"id": "f1", "from": "n2", "to": "n3"}},
                {"kind": "scheme-derive", "boardId": "b1", "newBoardId": "b3",
                 "name": "方案 B"},
            ],
        )
        derived = self.board(canvas_id, "b3")
        self.assertEqual(derived["name"], "方案 B")
        self.assertEqual(derived["scheme"]["derivedFrom"]["boardId"], "b1")
        self.assertEqual(len(derived["scheme"]["replaceableRegions"]), 1)
        source_ids = {node["id"] for node in self.board(canvas_id)["nodes"]}
        derived_ids = {node["id"] for node in derived["nodes"]}
        self.assertFalse(source_ids & derived_ids)
        # Children and flow endpoints were remapped, not left dangling.
        mapping = dict(zip(sorted(source_ids), sorted(derived_ids)))
        stack = next(node for node in derived["nodes"] if node["type"] == "stack")
        self.assertEqual(
            sorted(stack["children"]),
            sorted(
                node["id"]
                for node in derived["nodes"]
                if node["type"] in ("text", "button")
            ),
        )
        self.assertTrue(set(stack["children"]) <= derived_ids)
        self.assertEqual(len(derived["flowEdges"]), 1)
        self.assertIn(derived["flowEdges"][0]["from"], derived_ids)
        self.assertIn(derived["flowEdges"][0]["to"], derived_ids)
        self.assertTrue(mapping)
        # The source scheme is untouched, and validation accepts the pair.
        self.assertIsNone(self.board(canvas_id)["scheme"]["derivedFrom"])
        verdict = validate_canvas(
            parse_canvas(self.canvases.detail(self.project_id, canvas_id)["document"])
        )
        self.assertTrue(verdict["valid"])

    def test_deriving_onto_an_existing_board_id_is_refused(self) -> None:
        created = self.create_canvas()
        canvas_id = created["canvas"]["canvasId"]
        with self.assertRaises(WorkbenchError) as caught:
            self.apply_batch(
                canvas_id,
                [{"kind": "scheme-derive", "boardId": "b1", "newBoardId": "b2",
                  "name": "冲突"}],
            )
        self.assertEqual(caught.exception.code, INVALID_INPUT)


class SnapshotAndComparisonTest(OrchestrationTestCase):
    def test_a_fixed_snapshot_does_not_move_with_the_canvas(self) -> None:
        created = self.create_canvas()
        canvas_id = created["canvas"]["canvasId"]
        snapshot = self.orchestration.create_snapshot(
            self.project_id, canvas_id, note="评审基线",
            operation=self.operation({"action": "snapshots"}),
        )["result"]
        self.assertTrue(snapshot["frozen"])
        self.assertEqual(snapshot["nodeCount"], 3)
        self.assertEqual(snapshot["boardId"], "b1")

        # The canvas changes afterwards; the frozen hash stays the baseline.
        self.apply_batch(
            canvas_id,
            [{"kind": "node-add", "boardId": "b1",
              "node": {"id": "n9", "type": "text", "props": {"text": "新增"},
                       "layout": {"x": 0, "y": 0, "width": 100, "height": 30, "z": 9}}}],
        )
        frozen = self.orchestration.snapshot(
            self.project_id, canvas_id, snapshot["snapshotId"]
        )["snapshot"]
        self.assertEqual(frozen["contentHash"], snapshot["contentHash"])
        self.assertEqual(frozen["nodeCount"], 3)
        html = self.blobs.read(frozen["contentHash"]).decode("utf-8")
        self.assertIn("静态布局快照", html)
        listing = self.orchestration.list_snapshots(self.project_id, canvas_id)
        self.assertEqual(len(listing["snapshots"]), 1)

    def test_comparison_shows_differences_and_crowns_no_winner(self) -> None:
        created = self.create_canvas()
        canvas_id = created["canvas"]["canvasId"]
        first = self.orchestration.create_snapshot(
            self.project_id, canvas_id, note="A",
            operation=self.operation({"action": "snapshots"}),
        )["result"]
        self.apply_batch(
            canvas_id,
            [{"kind": "node-add", "boardId": "b2",
              "node": {"id": "p3", "type": "text", "props": {"text": "补充"},
                       "layout": {"x": 0, "y": 90, "width": 100, "height": 30, "z": 1}}}],
        )
        second = self.orchestration.create_snapshot(
            self.project_id, canvas_id, board_id="b2", note="B",
            operation=self.operation({"action": "snapshots"}),
        )["result"]
        compared = self.orchestration.compare(
            self.project_id, canvas_id, left=first["snapshotId"], right=second["snapshotId"],
            operation=self.operation({"action": "compare"}),
        )["result"]
        self.assertIsNone(compared["winner"])
        self.assertIsNone(compared["approval"])
        self.assertIn("不选择赢家", compared["note"])
        self.assertFalse(compared["differences"]["sameContent"])
        self.assertEqual(compared["differences"]["nodeCount"], {"left": 3, "right": 2})
        self.assertEqual(compared["left"]["contentHash"], first["contentHash"])
        counts = {row["type"]: row for row in compared["differences"]["nodeTypes"]}
        self.assertEqual(counts["text"]["left"], 1)
        self.assertEqual(counts["text"]["right"], 2)

        # Same snapshot on both sides, and a foreign snapshot: both refused.
        for left, right in (
            (first["snapshotId"], first["snapshotId"]),
            (first["snapshotId"], "00000000-0000-4000-8000-000000000000"),
        ):
            with self.subTest(right=right):
                with self.assertRaises(WorkbenchError) as caught:
                    self.orchestration.compare(
                        self.project_id, canvas_id, left=left, right=right,
                        operation=self.operation({"action": "compare"}),
                    )
                self.assertIn(caught.exception.code, (INVALID_INPUT, INVALID_TARGET))


class ContextSelectionTest(OrchestrationTestCase):
    def build(self, canvas_id: str, **kwargs) -> dict:
        return self.orchestration.build_context(
            self.project_id,
            canvas_id,
            node_ids=kwargs.pop("node_ids"),
            operation=self.operation({"action": "contexts", **kwargs}),
            **kwargs,
        )["result"]

    def test_the_selection_carries_what_would_be_sent_and_a_digest(self) -> None:
        created = self.create_canvas()
        canvas_id = created["canvas"]["canvasId"]
        asset = self.publish_markdown()
        revision = self.store.latest_revision(asset["assetId"])
        selection = self.build(canvas_id, node_ids=["n2"])
        self.assertEqual(selection["state"], "draft")
        self.assertEqual([node["nodeId"] for node in selection["nodes"]], ["n2"])
        self.assertEqual(selection["nodes"][0]["props"]["text"], "标题")
        self.assertEqual(selection["revisions"], [])
        self.assertEqual(selection["files"], [])
        self.assertTrue(selection["digest"].startswith("sha256:"))
        exclusions = {row["kind"]: row for row in selection["exclusions"]}
        for kind in (
            "unselected-nodes",
            "other-boards",
            "project-files",
            "run-and-evidence-logs",
            "credentials",
        ):
            self.assertIn(kind, exclusions)
        self.assertEqual(exclusions["unselected-nodes"]["count"], 2)
        self.assertEqual(selection["totals"]["revisionBytes"], 0)
        self.assertEqual(selection["totals"]["fileBytes"], 0)
        self.assertEqual(
            selection["totals"]["bytes"],
            selection["totals"]["nodeBytes"]
            + selection["totals"]["revisionBytes"]
            + selection["totals"]["fileBytes"],
        )

        # An explicitly named revision is fixed by id, not by "latest".
        with_revision = self.build(
            canvas_id, node_ids=["n2"], revision_ids=[revision["revision_id"]]
        )
        self.assertEqual(
            with_revision["revisions"][0]["revisionId"], revision["revision_id"]
        )
        self.assertEqual(with_revision["revisions"][0]["reason"], "显式加入的修订")
        self.assertTrue(with_revision["revisions"][0]["fixedRevision"])
        self.assertGreater(with_revision["totals"]["bytes"], selection["totals"]["bytes"])
        self.assertNotEqual(with_revision["digest"], selection["digest"])

    def test_instance_nodes_bring_their_fixed_revision_along(self) -> None:
        component = self.components.create_component(
            self.project_id,
            name="按钮",
            definition={"name": "按钮", "props": []},
            operation=self.operation({"action": "components"}),
        )["result"]
        self.components.publish(
            self.project_id, component["assetId"],
            operation=self.operation({"action": "component-publish"}),
        )
        instance = self.reuse.create_instance(
            self.project_id, component["assetId"],
            operation=self.operation({"action": "instances"}),
        )["result"]
        created = self.create_canvas()
        canvas_id = created["canvas"]["canvasId"]
        self.apply_batch(
            canvas_id,
            [{"kind": "node-add", "boardId": "b1",
              "node": {"id": "inst", "type": "instance",
                       "props": {"instanceId": instance["instanceId"]},
                       "layout": {"x": 0, "y": 0, "width": 200, "height": 80, "z": 5}}}],
        )
        selection = self.build(canvas_id, node_ids=["inst"])
        self.assertEqual(len(selection["revisions"]), 1)
        self.assertEqual(
            selection["revisions"][0]["reason"], "实例节点的固定修订"
        )
        self.assertEqual(
            selection["revisions"][0]["assetId"], component["assetId"]
        )

    def test_files_are_explicit_and_credentials_are_never_included(self) -> None:
        created = self.create_canvas()
        canvas_id = created["canvas"]["canvasId"]
        (self.project_dir / "notes.md").write_bytes(b"notes\n")
        selection = self.build(canvas_id, node_ids=["n2"], file_paths=["notes.md"])
        self.assertEqual(selection["files"][0]["path"], "notes.md")
        self.assertEqual(selection["files"][0]["size"], 6)
        self.assertTrue(selection["files"][0]["contentHash"].startswith("sha256:"))

        (self.project_dir / ".env").write_bytes(b"TOKEN=secret\n")
        with self.assertRaises(WorkbenchError) as caught:
            self.build(canvas_id, node_ids=["n2"], file_paths=[".env"])
        self.assertEqual(caught.exception.code, INVALID_INPUT)
        self.assertIn("凭据", str(caught.exception))
        with self.assertRaises(WorkbenchError) as caught:
            self.build(canvas_id, node_ids=["n2"], file_paths=["missing.md"])
        self.assertEqual(caught.exception.code, INVALID_TARGET)

    def test_unknown_content_and_empty_selections_are_refused(self) -> None:
        created = self.create_canvas()
        canvas_id = created["canvas"]["canvasId"]
        for kwargs, code in (
            ({"node_ids": ["ghost"]}, INVALID_TARGET),
            ({"node_ids": []}, INVALID_INPUT),
            ({"node_ids": ["n2"], "revision_ids": ["00000000-0000-4000-8000-000000000000"]},
             INVALID_TARGET),
            ({"node_ids": ["n2"], "revision_ids": "not-a-list"}, INVALID_INPUT),
        ):
            with self.subTest(kwargs=sorted(kwargs)):
                with self.assertRaises(WorkbenchError) as caught:
                    self.build(canvas_id, **kwargs)
                self.assertEqual(caught.exception.code, code)

    def test_a_change_after_confirmation_requires_a_new_confirmation(self) -> None:
        created = self.create_canvas()
        canvas_id = created["canvas"]["canvasId"]
        selection = self.build(canvas_id, node_ids=["n2"])
        confirmed = self.orchestration.confirm_context(
            self.project_id, canvas_id, selection["selectionId"],
            digest=selection["digest"],
            operation=self.operation({"action": "confirm"}),
        )["result"]
        self.assertEqual(confirmed["state"], "confirmed")
        self.assertEqual(confirmed["confirmed"]["digest"], selection["digest"])
        self.assertFalse(confirmed["staleConfirmation"])

        # A stale digest is a conflict, not a silent re-confirmation.
        with self.assertRaises(WorkbenchError) as caught:
            self.orchestration.confirm_context(
                self.project_id, canvas_id, selection["selectionId"],
                digest="sha256:" + "0" * 64,
                operation=self.operation({"action": "confirm"}),
            )
        self.assertEqual(caught.exception.code, CONFLICT)
        self.assertEqual(
            self.store.context_selection(selection["selectionId"])["state"],
            "confirmed",
        )

        changed = self.orchestration.build_context(
            self.project_id,
            canvas_id,
            selection_id=selection["selectionId"],
            node_ids=["n2", "n3"],
            operation=self.operation({"action": "contexts"}),
        )["result"]
        self.assertEqual(changed["state"], "draft")
        self.assertTrue(changed["staleConfirmation"])
        self.assertEqual(changed["confirmed"]["digest"], selection["digest"])
        self.assertNotEqual(changed["digest"], selection["digest"])
        with self.assertRaises(WorkbenchError) as caught:
            self.orchestration.confirm_context(
                self.project_id, canvas_id, selection["selectionId"],
                digest=selection["digest"],
                operation=self.operation({"action": "confirm"}),
            )
        self.assertEqual(caught.exception.code, CONFLICT)

        # Reads show the serialized selection, and the digest matches content.
        read = self.orchestration.context(self.project_id, selection["selectionId"])[
            "selection"
        ]
        self.assertEqual(read["totals"]["nodeCount"], 2)
        self.assertEqual(read["canvasCounter"], self.canvas_counter(canvas_id))

    def test_reads_are_scoped_to_their_own_project_and_canvas(self) -> None:
        created = self.create_canvas()
        canvas_id = created["canvas"]["canvasId"]
        other = self.create_canvas({**CANVAS, "name": "另一个"})
        other_canvas_id = other["canvas"]["canvasId"]
        snapshot = self.orchestration.create_snapshot(
            self.project_id, canvas_id,
            operation=self.operation({"action": "snapshots"}),
        )["result"]
        selection = self.build(canvas_id, node_ids=["n2"])

        other_dir = self.base / "other"
        other_dir.mkdir()
        candidate = self.service.probe_folder(other_dir)
        second = self.service.register_project(
            path=candidate.canonical_path,
            candidate_id=candidate.candidate_id,
            name="Other",
            operation=self.operation({"action": "register-project"}),
        )["result"]
        # Another project cannot read this selection or its snapshots.
        with self.assertRaises(WorkbenchError) as caught:
            self.orchestration.context(second["projectId"], selection["selectionId"])
        self.assertEqual(caught.exception.code, INVALID_TARGET)
        with self.assertRaises(WorkbenchError) as caught:
            self.orchestration.snapshot(
                second["projectId"], canvas_id, snapshot["snapshotId"]
            )
        self.assertEqual(caught.exception.code, INVALID_TARGET)
        # A snapshot belongs to its own canvas, not to every canvas of the
        # project: naming it from a sibling canvas is an invalid target.
        with self.assertRaises(WorkbenchError) as caught:
            self.orchestration.snapshot(
                self.project_id, other_canvas_id, snapshot["snapshotId"]
            )
        self.assertEqual(caught.exception.code, INVALID_TARGET)
        with self.assertRaises(WorkbenchError) as caught:
            self.orchestration.compare(
                self.project_id,
                other_canvas_id,
                left=snapshot["snapshotId"],
                right=snapshot["snapshotId"],
                operation=self.operation({"action": "compare"}),
            )
        self.assertEqual(caught.exception.code, INVALID_INPUT)


if __name__ == "__main__":  # pragma: no cover - manual run
    unittest.main()
