#!/usr/bin/env python3
"""A08: component definitions, native layouts, and distill candidates.

The rules under test are the ones R08 names: one schema for a component and
one for a native layout tree; an invalid property schema, default, slot, or
dependency blocks publication; an instance is validated by the same code
that renders its sample; a distilled candidate stays a candidate and never
touches the page it came from.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from design_playbook_workbench.assets import AssetService
from design_playbook_workbench.blobs import BlobStore
from design_playbook_workbench.components import (
    ComponentService,
    check_params,
    instance_html,
    parse_definition,
    parse_layout,
    validate_definition,
    validate_layout,
)
from design_playbook_workbench.errors import (
    INVALID_INPUT,
    INVALID_TARGET,
    LIMIT_EXCEEDED,
    MISSING_DEPENDENCY,
    UNSUPPORTED,
    WorkbenchError,
)
from design_playbook_workbench.reuse import ReuseService
from design_playbook_workbench.service import Operation, WorkbenchService
from design_playbook_workbench.store import Store, WorkbenchDataDirectory

DEFINITION = {
    "name": "Button",
    "description": "主要操作按钮",
    "props": [
        {"name": "label", "type": "string", "default": "确定"},
        {"name": "tone", "type": "enum", "values": ["primary", "ghost"], "default": "primary"},
        {"name": "disabled", "type": "boolean", "default": False},
        {"name": "fontSize", "type": "number", "default": 16},
        {"name": "iconAsset", "type": "asset"},
    ],
    "variants": [{"name": "size", "values": ["s", "m", "l"]}],
    "states": ["default", "hover", "disabled"],
    "slots": [{"name": "icon", "required": False, "description": "图标位"}],
    "constraints": {"minWidth": "4rem", "aspectRatio": "auto"},
    "docs": "只声明公开面：内部图层不属于公开契约。",
}

PAGE = {
    "name": "首页",
    "nodes": [
        {"id": "root", "type": "stack", "children": ["title", "slot-1"],
         "props": {"direction": "vertical", "gap": "8px"}},
        {"id": "title", "type": "text", "props": {"text": "欢迎"}},
        {"id": "slot-1", "type": "slot", "props": {"name": "hero"}},
    ],
}


class ComponentsTestCase(unittest.TestCase):
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
        self.grant(["read", "write"])

    def tearDown(self) -> None:
        self.store.close()
        self._tmp.cleanup()

    def operation(self, payload: dict) -> Operation:
        self._operations += 1
        return Operation(
            operation_id=f"op_comp_{self._operations:08d}", payload=payload
        )

    def grant(self, scopes: list[str]) -> None:
        counter = int(self.store.project(self.project_id)["counter"])
        self.service.set_grants(
            self.project_id,
            scopes=scopes,
            operation=Operation(
                operation_id=f"op_grant_{self._operations:08d}",
                payload={"scopes": scopes},
                expected_counter=counter,
            ),
        )

    def create_component(self, definition: dict, name: str = "Button") -> dict:
        return self.components.create_component(
            self.project_id,
            name=name,
            definition=definition,
            operation=self.operation({"action": "components", "name": name}),
        )["result"]

    def create_page(self, layout: dict, name: str = "首页") -> dict:
        return self.components.create_page(
            self.project_id,
            name=name,
            layout=layout,
            operation=self.operation({"action": "pages", "name": name}),
        )["result"]


class DefinitionRulesTest(ComponentsTestCase):
    def test_a_valid_definition_round_trips_into_types(self) -> None:
        definition = parse_definition(DEFINITION)
        self.assertEqual(
            [prop["name"] for prop in definition["props"]],
            ["label", "tone", "disabled", "fontSize", "iconAsset"],
        )
        self.assertEqual(definition["variants"][0]["values"], ["s", "m", "l"])
        self.assertTrue(validate_definition(definition)["valid"])

    def test_unknown_fields_types_and_limits_are_refused(self) -> None:
        for raw in (
            {"name": "B", "props": [{"name": "x", "type": "color"}]},
            {"name": "B", "scroll": True},
            {"name": "B", "props": "nope"},
            "[]",
            None,
        ):
            with self.subTest(raw=raw):
                with self.assertRaises(WorkbenchError) as caught:
                    parse_definition(raw)
                self.assertIn(caught.exception.code, (INVALID_INPUT, UNSUPPORTED))
        over = {"name": "B", "props": [
            {"name": f"p{index}", "type": "string"} for index in range(201)
        ]}
        with self.assertRaises(WorkbenchError) as caught:
            parse_definition(over)
        self.assertEqual(caught.exception.code, LIMIT_EXCEEDED)

    def test_bad_defaults_variants_slots_and_constraints_are_reported(self) -> None:
        verdict = validate_definition(
            parse_definition(
                {
                    "name": "B",
                    "props": [
                        {"name": "tone", "type": "enum", "values": ["a"], "default": "z"},
                        {"name": "size", "type": "number", "default": "big"},
                        {"name": "dup", "type": "string"},
                        {"name": "dup", "type": "string"},
                        {"name": "1bad", "type": "string"},
                    ],
                    "variants": [
                        {"name": "size", "values": ["s"]},
                        {"name": "size", "values": ["m"]},
                        {"name": "empty", "values": []},
                    ],
                    "states": ["hover", "hover"],
                    "slots": [{"name": "icon"}, {"name": "icon"}],
                    "constraints": {"maxWidth": "wide", "rotate": "3deg"},
                }
            )
        )
        kinds = {(error["path"], error["kind"]) for error in verdict["errors"]}
        self.assertIn(("props.tone", "invalid-default"), kinds)
        self.assertIn(("props.size", "invalid-default"), kinds)
        self.assertIn(("props.dup", "duplicate-prop"), kinds)
        self.assertIn(("props.1bad", "invalid-prop-name"), kinds)
        self.assertIn(("variants.size", "duplicate-variant"), kinds)
        self.assertIn(("variants.empty", "invalid-variant"), kinds)
        self.assertIn(("states.hover", "duplicate-state"), kinds)
        self.assertIn(("slots.icon", "duplicate-slot"), kinds)
        self.assertIn(("constraints.maxWidth", "invalid-constraint"), kinds)
        self.assertIn(("constraints.rotate", "invalid-constraint"), kinds)
        self.assertFalse(verdict["valid"])

    def test_variant_shadowing_a_property_is_refused(self) -> None:
        verdict = validate_definition(
            parse_definition(
                {
                    "name": "B",
                    "props": [{"name": "size", "type": "string", "default": "m"}],
                    "variants": [{"name": "size", "values": ["s", "m"]}],
                }
            )
        )
        self.assertIn("variant-shadows-prop", [e["kind"] for e in verdict["errors"]])

    def test_missing_names_are_reported(self) -> None:
        verdict = validate_definition(parse_definition({"name": "  "}))
        self.assertEqual([error["kind"] for error in verdict["errors"]], ["missing-name"])


class ComponentLifecycleTest(ComponentsTestCase):
    def test_creating_a_component_is_a_draft_with_no_project_write(self) -> None:
        created = self.create_component(DEFINITION)
        self.assertEqual(created["kind"], "component")
        self.assertEqual(created["lifecycle"], "draft")
        self.assertIsNone(created["revisionNumber"])
        self.assertEqual(
            [entry["path"] for entry in created["manifest"]], ["Button.component.json"]
        )
        self.assertEqual(list(self.project_dir.iterdir()), [])
        detail = self.components.component(self.project_id, created["assetId"])
        self.assertTrue(detail["validation"]["valid"])
        self.assertEqual(detail["source"], {"kind": "draft"})

    def test_an_invalid_definition_is_refused_before_anything_is_written(self) -> None:
        broken = dict(DEFINITION, props=[{"name": "tone", "type": "enum",
                                          "values": ["a"], "default": "z"}])
        with self.assertRaises(WorkbenchError) as caught:
            self.create_component(broken)
        self.assertEqual(caught.exception.code, INVALID_INPUT)
        self.assertIn("invalid-default", str(caught.exception))
        self.assertEqual(self.store.project_assets(self.project_id), [])

    def test_publishing_records_resolved_dependencies(self) -> None:
        token_asset = self._tokens_asset()
        component = self.create_component(DEFINITION)
        definition = dict(
            DEFINITION,
            dependencies={"tokens": [token_asset], "components": []},
        )
        updated = self.components.update_definition(
            self.project_id,
            component["assetId"],
            definition=definition,
            operation=self.operation({"action": "component-update"}),
        )
        self.assertTrue(updated["result"]["validation"]["valid"])
        published = self.components.publish(
            self.project_id,
            component["assetId"],
            operation=self.operation({"action": "component-publish"}),
        )
        self.assertEqual(published["result"]["revisionNumber"], 1)
        revision = self.store.latest_revision(component["assetId"])
        rows = self.store.dependencies(revision["revision_id"])
        self.assertEqual([row["depends_on_asset_id"] for row in rows], [token_asset])
        # The recorded locator is typed, not a pretend project file.
        locators = json.loads(revision["source_locators_json"])
        self.assertEqual(locators, [])

    def test_publish_refuses_unresolved_dependencies_and_unverified_capabilities(
        self,
    ) -> None:
        component = self.create_component(DEFINITION)
        missing = dict(
            DEFINITION,
            dependencies={"tokens": [], "components": ["00000000-0000-4000-8000-000000000000"]},
        )
        self.components.update_definition(
            self.project_id,
            component["assetId"],
            definition=missing,
            operation=self.operation({"action": "component-update"}),
        )
        with self.assertRaises(WorkbenchError) as caught:
            self.components.publish(
                self.project_id,
                component["assetId"],
                operation=self.operation({"action": "component-publish"}),
            )
        self.assertEqual(caught.exception.code, MISSING_DEPENDENCY)
        self.assertEqual(self.store.asset_revisions(component["assetId"]), [])

        # A misleading verified capability never publishes without a record.
        draft = self.store.draft(component["assetId"])
        attributes = json.loads(draft["attributes_json"])
        attributes["capabilities"] = ["reference", "runnable-verified"]
        self.store.update_draft(
            asset_id=component["assetId"],
            tags=[],
            attributes=attributes,
            now="2026-09-26T12:00:00Z",
        )
        with self.assertRaises(WorkbenchError) as caught:
            self.components.publish(
                self.project_id,
                component["assetId"],
                operation=self.operation({"action": "component-publish-2"}),
            )
        self.assertEqual(caught.exception.code, MISSING_DEPENDENCY)
        self.assertEqual(self.store.asset_revisions(component["assetId"]), [])

    def test_a_component_cannot_depend_on_itself(self) -> None:
        component = self.create_component(DEFINITION)
        self.components.update_definition(
            self.project_id,
            component["assetId"],
            definition=dict(
                DEFINITION,
                dependencies={"tokens": [], "components": [component["assetId"]]},
            ),
            operation=self.operation({"action": "component-update"}),
        )
        detail = self.components.component(self.project_id, component["assetId"])
        self.assertIn(
            "self-dependency", [e["kind"] for e in detail["validation"]["errors"]]
        )
        self.assertFalse(detail["validation"]["valid"])
        with self.assertRaises(WorkbenchError) as caught:
            self.components.publish(
                self.project_id,
                component["assetId"],
                operation=self.operation({"action": "component-publish"}),
            )
        self.assertEqual(caught.exception.code, MISSING_DEPENDENCY)
        self.assertEqual(self.store.asset_revisions(component["assetId"]), [])

    def _tokens_asset(self) -> str:
        folder = self.project_dir / "tokens"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "brand.json").write_bytes(b'{"color": {"brand": "#1f4fd8"}}')
        imported = self.assets.import_selection(
            self.project_id,
            selections=["tokens/brand.json"],
            operation=self.operation({"action": "imports"}),
        )["result"]["asset"]
        self.assets.publish_revision(
            self.project_id,
            imported["assetId"],
            operation=self.operation({"action": "publish"}),
        )
        return imported["assetId"]


class InstancePreviewTest(ComponentsTestCase):
    def test_parameters_are_validated_against_the_public_schema(self) -> None:
        definition = parse_definition(DEFINITION)
        self.assertEqual(check_params(definition, {"label": "好的"}), [])
        self.assertEqual(
            [error["kind"] for error in check_params(definition, {"unknown": 1})],
            ["unknown-param"],
        )
        self.assertEqual(
            [error["kind"] for error in check_params(definition, {"label": 7})],
            ["invalid-param-value"],
        )
        self.assertEqual(
            [error["kind"] for error in check_params(definition, {"tone": "nope"})],
            ["invalid-param-value"],
        )
        self.assertEqual(
            [error["kind"] for error in check_params(definition, {"iconAsset": ""})],
            ["invalid-param-value"],
        )
        self.assertEqual(
            [error["kind"] for error in check_params(definition, {"disabled": 0})],
            ["invalid-param-value"],
        )
        required = parse_definition(
            {"name": "R", "props": [{"name": "title", "type": "string", "required": True}]}
        )
        self.assertEqual(
            [error["kind"] for error in check_params(required, {})], ["missing-param"]
        )

    def test_the_sample_uses_the_resolved_values_and_states_the_limit(self) -> None:
        html = instance_html(parse_definition(DEFINITION), {"label": "保存"})
        self.assertIn("保存", html)
        self.assertIn("primary", html)
        self.assertIn("不是源码组件运行结果", html)
        self.assertIn("default", html)
        self.assertIn("hover", html)
        self.assertIn("disabled", html)

    def test_the_preview_route_shape_over_the_service(self) -> None:
        component = self.create_component(DEFINITION)
        preview = self.components.instance_preview(
            self.project_id, component["assetId"], params={"label": "保存"}
        )
        self.assertEqual(preview["params"]["label"], "保存")
        self.assertEqual(preview["params"]["tone"], "primary")
        self.assertEqual(preview["unsetParams"], ["iconAsset"])
        self.assertEqual(preview["declared"]["slots"], ["icon"])
        self.assertIn("组件源码未执行", preview["limitations"])
        with self.assertRaises(WorkbenchError) as caught:
            self.components.instance_preview(
                self.project_id, component["assetId"], params={"label": 7}
            )
        self.assertEqual(caught.exception.code, INVALID_INPUT)

    def test_non_component_assets_cannot_use_the_component_routes(self) -> None:
        page = self.create_page(PAGE)
        with self.assertRaises(WorkbenchError) as caught:
            self.components.instance_preview(self.project_id, page["assetId"])
        self.assertEqual(caught.exception.code, UNSUPPORTED)
        with self.assertRaises(WorkbenchError) as caught:
            self.components.component(self.project_id, page["assetId"])
        self.assertEqual(caught.exception.code, UNSUPPORTED)


class PageLayoutTest(ComponentsTestCase):
    def test_a_layout_tree_round_trips_and_validates(self) -> None:
        layout = parse_layout(PAGE)
        verdict = validate_layout(layout)
        self.assertTrue(verdict["valid"])
        self.assertEqual(verdict["nodeIds"], ["root", "slot-1", "title"])
        self.assertEqual(verdict["roots"], ["root"])

    def test_broken_trees_are_reported_by_kind(self) -> None:
        broken = {
            "nodes": [
                {"id": "a", "type": "stack", "children": ["b", "ghost"]},
                {"id": "b", "type": "text", "children": ["a"], "props": {}},
                {"id": "a", "type": "text", "props": {"text": "dup"}},
                {"id": "c", "type": "image", "props": {}},
                {"id": "d", "type": "button", "props": {}},
                {"id": "e", "type": "slot", "props": {}},
                {"id": "f", "type": "stack", "props": {"rotate": "3deg"}},
            ]
        }
        verdict = validate_layout(parse_layout(broken))
        kinds = {error["kind"] for error in verdict["errors"]}
        self.assertIn("unknown-child", kinds)
        self.assertIn("duplicate-node", kinds)
        self.assertIn("node-cycle", kinds)
        self.assertIn("missing-node-payload", kinds)
        self.assertIn("unknown-node-field", kinds)
        self.assertFalse(verdict["valid"])
        with self.assertRaises(WorkbenchError) as caught:
            parse_layout({"nodes": [{"id": "a", "type": "canvas"}]})
        self.assertEqual(caught.exception.code, UNSUPPORTED)

    def test_instance_nodes_resolve_published_components_with_valid_params(
        self,
    ) -> None:
        component = self.create_component(DEFINITION)
        page = {
            "name": "P",
            "nodes": [
                {"id": "root", "type": "stack", "children": ["btn"], "props": {}},
                {"id": "btn", "type": "instance",
                 "props": {"assetId": component["assetId"], "params": {"label": "保存"}}},
            ],
        }
        unpublished = parse_layout(page)
        verdict = validate_layout(unpublished)
        self.assertIn("unresolved-instance", [e["kind"] for e in verdict["errors"]])
        with self.assertRaises(WorkbenchError) as caught:
            self.create_page(page)
        self.assertEqual(caught.exception.code, INVALID_INPUT)
        self.assertIn("unpublished-instance", str(caught.exception))

        self.components.publish(
            self.project_id, component["assetId"],
            operation=self.operation({"action": "component-publish"}),
        )
        created = self.create_page(page)
        detail = self.components.page_layout(self.project_id, created["assetId"])
        self.assertTrue(detail["validation"]["valid"])

        wrong_params = json.loads(json.dumps(page))
        wrong_params["nodes"][1]["props"]["params"] = {"label": 7}
        with self.assertRaises(WorkbenchError) as caught:
            self.create_page(wrong_params, name="坏的")
        self.assertEqual(caught.exception.code, INVALID_INPUT)
        unknown_instance = json.loads(json.dumps(page))
        unknown_instance["nodes"][1]["props"]["assetId"] = (
            "00000000-0000-4000-8000-000000000000"
        )
        with self.assertRaises(WorkbenchError):
            self.create_page(unknown_instance, name="未知实例")

    def test_pages_publish_their_own_document(self) -> None:
        page = self.create_page(PAGE)
        self.assertEqual(
            self.components.page_layout(self.project_id, page["assetId"])["source"],
            {"kind": "draft"},
        )
        published = self.components.publish_page(
            self.project_id, page["assetId"],
            operation=self.operation({"action": "page-publish"}),
        )
        self.assertEqual(published["result"]["revisionNumber"], 1)
        self.assertTrue(published["result"]["validation"]["valid"])
        after = self.components.page_layout(self.project_id, page["assetId"])
        self.assertEqual(after["source"]["kind"], "revision")
        self.assertEqual(after["source"]["revisionNumber"], 1)

    def test_non_page_assets_cannot_be_read_as_pages(self) -> None:
        component = self.create_component(DEFINITION)
        with self.assertRaises(WorkbenchError) as caught:
            self.components.page_layout(self.project_id, component["assetId"])
        self.assertEqual(caught.exception.code, UNSUPPORTED)


class DistillCandidateTest(ComponentsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.page = self.create_page(PAGE)
        self.components.publish_page(
            self.project_id,
            self.page["assetId"],
            operation=self.operation({"action": "page-publish"}),
        )
        self.page_revision = self.store.latest_revision(self.page["assetId"])
        self.before_layout = self._page_bytes()

    def _page_bytes(self) -> bytes:
        detail = self.components.page_layout(self.project_id, self.page["assetId"])
        return json.dumps(detail["layout"], sort_keys=True).encode("utf-8")

    def test_a_candidate_names_its_source_and_stays_unpublished(self) -> None:
        outcome = self.components.distill_candidate(
            self.project_id,
            self.page["assetId"],
            node_ids=["title"],
            name="标题块",
            operation=self.operation({"action": "distill-candidate"}),
        )
        result = outcome["result"]
        candidate = result["candidate"]
        self.assertEqual(candidate["fromAssetId"], self.page["assetId"])
        self.assertEqual(candidate["fromRevisionId"], self.page_revision["revision_id"])
        self.assertEqual(candidate["nodeIds"], ["title"])
        self.assertFalse(candidate["complete"])
        locator = result["sourceLocator"]
        self.assertEqual(locator["objectType"], "revision")
        self.assertEqual(locator["sourceHash"], self.page_revision["content_hash"])
        self.assertIn("源页面未被修改", result["ownerNote"])

        # The candidate is a draft and cannot be published as-is.
        detail = self.components.component(self.project_id, result["assetId"])
        self.assertIn(
            "incomplete-candidate", [e["kind"] for e in detail["validation"]["errors"]]
        )
        with self.assertRaises(WorkbenchError) as caught:
            self.components.publish(
                self.project_id,
                result["assetId"],
                operation=self.operation({"action": "component-publish"}),
            )
        self.assertEqual(caught.exception.code, INVALID_INPUT)
        self.assertEqual(self.store.asset_revisions(result["assetId"]), [])

        # The source page is untouched: same stored layout, no new revision.
        self.assertEqual(self._page_bytes(), self.before_layout)
        self.assertEqual(len(self.store.asset_revisions(self.page["assetId"])), 1)

    def test_a_completed_candidate_publishes_with_its_own_surface(self) -> None:
        result = self.components.distill_candidate(
            self.project_id,
            self.page["assetId"],
            node_ids=["root"],
            operation=self.operation({"action": "distill-candidate"}),
        )["result"]
        self.components.update_definition(
            self.project_id,
            result["assetId"],
            definition={
                "name": "标题块",
                "description": "补全后的候选",
                "props": [{"name": "title", "type": "string", "default": "欢迎"}],
                "slots": [{"name": "hero"}],
                "candidate": {
                    "fromAssetId": self.page["assetId"],
                    "fromRevisionId": self.page_revision["revision_id"],
                    "nodeIds": result["candidate"]["nodeIds"],
                    "complete": True,
                },
            },
            operation=self.operation({"action": "component-update"}),
        )
        published = self.components.publish(
            self.project_id,
            result["assetId"],
            operation=self.operation({"action": "component-publish"}),
        )
        self.assertEqual(published["result"]["revisionNumber"], 1)
        self.assertNotIn(
            "runnable-verified", published["result"]["capabilities"]
        )
        self.assertEqual(self._page_bytes(), self.before_layout)

    def test_unknown_blocks_and_foreign_pages_are_refused(self) -> None:
        with self.assertRaises(WorkbenchError) as caught:
            self.components.distill_candidate(
                self.project_id,
                self.page["assetId"],
                node_ids=["ghost"],
                operation=self.operation({"action": "distill-bad"}),
            )
        self.assertEqual(caught.exception.code, INVALID_TARGET)
        component = self.create_component(DEFINITION)
        with self.assertRaises(WorkbenchError) as caught:
            self.components.distill_candidate(
                self.project_id,
                component["assetId"],
                node_ids=["root"],
                operation=self.operation({"action": "distill-wrong-kind"}),
            )
        self.assertEqual(caught.exception.code, UNSUPPORTED)
        with self.assertRaises(WorkbenchError) as caught:
            self.components.distill_candidate(
                self.project_id,
                self.page["assetId"],
                node_ids=[],
                operation=self.operation({"action": "distill-empty"}),
            )
        self.assertEqual(caught.exception.code, INVALID_INPUT)


if __name__ == "__main__":  # pragma: no cover - manual run
    unittest.main()
