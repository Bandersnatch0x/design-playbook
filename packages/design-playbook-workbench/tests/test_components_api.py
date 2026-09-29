#!/usr/bin/env python3
"""A08 over the real API: component documents, layouts, and candidates.

The domain rules live in ``test_components.py``; these tests prove the
distributed surface is the same contract -- routes, capability scopes,
documented error codes, and mutation replay.
"""
from __future__ import annotations

import json
import unittest
from urllib.parse import quote

from tests.harness import WorkbenchHarness, http_request

DEFINITION = {
    "name": "Button",
    "description": "主要操作按钮",
    "props": [
        {"name": "label", "type": "string", "default": "确定"},
        {"name": "tone", "type": "enum", "values": ["primary", "ghost"], "default": "primary"},
    ],
    "variants": [{"name": "size", "values": ["s", "m", "l"]}],
    "states": ["default", "hover"],
    "slots": [{"name": "icon"}],
}

PAGE = {
    "name": "首页",
    "nodes": [
        {"id": "root", "type": "stack", "children": ["title"], "props": {}},
        {"id": "title", "type": "text", "props": {"text": "欢迎"}},
    ],
}


class ComponentApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.h = WorkbenchHarness()
        self.addCleanup(self.h.stop)
        self.project_dir = self.h.make_directory("components")
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
        project_id: str,
        verb: str,
        *,
        asset_id: str | None = None,
        payload: dict | None = None,
        operation_id: str | None = None,
        capability: str | None = None,
    ):
        self._operations += 1
        operation = {
            "operationId": operation_id or f"op_api_{verb}_{self._operations:04d}",
            "payload": {"action": verb, **({"assetId": asset_id} if asset_id else {}), **(payload or {})},
        }
        path = (
            f"/api/v1/projects/{project_id}/actions/assets/{asset_id}/{verb}"
            if asset_id
            else f"/api/v1/projects/{project_id}/actions/{verb}"
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

    def view(
        self,
        view: str,
        *,
        asset_id: str,
        project_id: str | None = None,
        query: str = "",
        capability: str | None = None,
    ):
        suffix = "?" + query if query else ""
        return http_request(
            self.h.runtime,
            f"/api/v1/projects/{project_id or self.project_id}"
            f"/assets/{asset_id}/document/{view}{suffix}",
            token=None if capability else self.h.token,
            capability=capability,
        )

    def create_component(self, definition: dict = DEFINITION, *, name: str = "Button") -> dict:
        response = self.post(
            self.project_id, "components", payload={"name": name, "definition": definition}
        )
        assert response.status == 200, response.text
        return response.json["result"]

    def create_page(self, layout: dict = PAGE, *, name: str = "首页") -> dict:
        response = self.post(
            self.project_id, "pages", payload={"name": name, "layout": layout}
        )
        assert response.status == 200, response.text
        return response.json["result"]


class ComponentApiTest(ComponentApiTestCase):
    def test_the_definition_round_trips_through_the_document_view(self) -> None:
        component = self.create_component()
        document = self.view("component", asset_id=component["assetId"])
        self.assertEqual(document.status, 200, document.text)
        self.assertTrue(document.json["validation"]["valid"])
        self.assertEqual(document.json["source"], {"kind": "draft"})
        self.assertEqual(document.json["definition"]["props"][0]["name"], "label")
        self.assertEqual(
            [entry["path"] for entry in component["manifest"]],
            ["Button.component.json"],
        )

    def test_the_instance_view_renders_parameters_on_the_preview_origin(self) -> None:
        component = self.create_component()
        params = quote(json.dumps({"label": "保存"}, ensure_ascii=False))
        preview = self.view(
            "instance", asset_id=component["assetId"], query=f"params={params}"
        )
        self.assertEqual(preview.status, 200, preview.text)
        self.assertEqual(preview.json["params"]["label"], "保存")
        self.assertEqual(preview.json["params"]["tone"], "primary")
        self.assertEqual(preview.json["declared"]["slots"], ["icon"])
        self.assertEqual(preview.json["previewOrigin"], self.h.preview_origin)
        self.assertTrue(preview.json["previewUrl"].startswith(self.h.preview_origin))
        self.assertIn("组件源码未执行", preview.json["limitations"])

        bad_json = self.view(
            "instance", asset_id=component["assetId"], query="params=%7Bnope"
        )
        self.assertEqual(bad_json.status, 400)
        self.assertEqual(bad_json.error_code, "invalid-input")
        unknown = self.view(
            "instance",
            asset_id=component["assetId"],
            query="params=" + quote(json.dumps({"nope": 1})),
        )
        self.assertEqual(unknown.status, 400)
        self.assertEqual(unknown.error_code, "invalid-input")

    def test_edits_validate_first_and_replay_by_operation_id(self) -> None:
        component = self.create_component()
        broken = dict(DEFINITION, props=[{"name": "tone", "type": "enum",
                                          "values": ["a"], "default": "z"}])
        refused = self.post(
            self.project_id,
            "component-update",
            asset_id=component["assetId"],
            payload={"definition": broken},
            operation_id="op_api_comp_edit_1",
        )
        self.assertEqual(refused.status, 400, refused.text)
        self.assertEqual(refused.error_code, "invalid-input")
        self.assertIn("invalid-default", refused.text)

        updated = self.post(
            self.project_id,
            "component-update",
            asset_id=component["assetId"],
            payload={"definition": DEFINITION},
            operation_id="op_api_comp_edit_2",
        )
        self.assertEqual(updated.status, 200, updated.text)
        self.assertFalse(updated.json["replayed"])
        replay = self.post(
            self.project_id,
            "component-update",
            asset_id=component["assetId"],
            payload={"definition": DEFINITION},
            operation_id="op_api_comp_edit_2",
        )
        self.assertEqual(replay.status, 200, replay.text)
        self.assertTrue(replay.json["replayed"])
        conflict = self.post(
            self.project_id,
            "component-update",
            asset_id=component["assetId"],
            payload={"definition": dict(DEFINITION, description="改过的")},
            operation_id="op_api_comp_edit_2",
        )
        self.assertEqual(conflict.status, 409)
        self.assertEqual(conflict.error_code, "conflict")

    def test_publishing_refuses_an_incomplete_dependency_and_then_succeeds(self) -> None:
        component = self.create_component()
        self.post(
            self.project_id,
            "component-update",
            asset_id=component["assetId"],
            payload={
                "definition": dict(
                    DEFINITION,
                    dependencies={
                        "tokens": [],
                        "components": ["00000000-0000-4000-8000-000000000000"],
                    },
                )
            },
        )
        refused = self.post(
            self.project_id, "component-publish", asset_id=component["assetId"]
        )
        self.assertEqual(refused.status, 422, refused.text)
        self.assertEqual(refused.error_code, "missing-dependency")

        self.post(
            self.project_id,
            "component-update",
            asset_id=component["assetId"],
            payload={"definition": DEFINITION},
        )
        published = self.post(
            self.project_id, "component-publish", asset_id=component["assetId"]
        )
        self.assertEqual(published.status, 200, published.text)
        self.assertEqual(published.json["result"]["revisionNumber"], 1)
        after = self.view("component", asset_id=component["assetId"])
        self.assertEqual(after.json["source"]["kind"], "revision")
        self.assertEqual(after.json["source"]["revisionNumber"], 1)

    def test_a_page_layout_can_be_published_and_read_back(self) -> None:
        page = self.create_page()
        document = self.view("page", asset_id=page["assetId"])
        self.assertEqual(document.status, 200, document.text)
        self.assertTrue(document.json["validation"]["valid"])
        self.assertEqual(document.json["layout"]["nodes"][0]["id"], "root")
        published = self.post(
            self.project_id, "page-publish", asset_id=page["assetId"]
        )
        self.assertEqual(published.status, 200, published.text)
        self.assertEqual(published.json["result"]["revisionNumber"], 1)

    def test_the_routes_refuse_unknown_views_and_wrong_asset_kinds(self) -> None:
        component = self.create_component()
        page = self.create_page()
        unknown = self.view("nonsense", asset_id=component["assetId"])
        self.assertEqual(unknown.status, 404)
        extra = self.view("component", asset_id=component["assetId"], query="x=1")
        self.assertEqual(extra.status, 400)
        self.assertEqual(extra.error_code, "invalid-input")
        wrong_kind = self.view("component", asset_id=page["assetId"])
        self.assertEqual(wrong_kind.status, 400)
        self.assertEqual(wrong_kind.error_code, "unsupported")
        foreign = self.view(
            "component", asset_id=component["assetId"], project_id=self.other_id
        )
        self.assertEqual(foreign.status, 400)
        self.assertEqual(foreign.error_code, "invalid-target")


class DistillApiTest(ComponentApiTestCase):
    def test_a_candidate_is_created_and_publishing_it_stays_refused(self) -> None:
        page = self.create_page()
        before = self.view("page", asset_id=page["assetId"]).json["layout"]
        published = self.post(
            self.project_id, "page-publish", asset_id=page["assetId"]
        )
        self.assertEqual(published.status, 200, published.text)
        response = self.post(
            self.project_id,
            "distill-candidate",
            asset_id=page["assetId"],
            payload={"sourcePageAssetId": page["assetId"], "nodeIds": ["title"], "name": "标题块"},
        )
        self.assertEqual(response.status, 200, response.text)
        result = response.json["result"]
        self.assertFalse(result["candidate"]["complete"])
        self.assertEqual(result["candidate"]["fromAssetId"], page["assetId"])
        self.assertEqual(result["sourceLocator"]["objectType"], "revision")
        self.assertIn("源页面未被修改", result["ownerNote"])

        refused = self.post(
            self.project_id, "component-publish", asset_id=result["assetId"]
        )
        self.assertEqual(refused.status, 400, refused.text)
        self.assertEqual(refused.error_code, "invalid-input")
        self.assertIn("incomplete-candidate", refused.text)

        after = self.view("page", asset_id=page["assetId"]).json["layout"]
        self.assertEqual(after, before)
        self.assertEqual(
            self.h.runtime.store.asset_revisions(page["assetId"]).__len__(), 1
        )

    def test_a_missing_source_page_or_block_is_refused(self) -> None:
        page = self.create_page()
        missing_nodes = self.post(
            self.project_id,
            "distill-candidate",
            asset_id=page["assetId"],
            payload={"sourcePageAssetId": page["assetId"], "nodeIds": []},
        )
        self.assertEqual(missing_nodes.status, 400)
        ghost = self.post(
            self.project_id,
            "distill-candidate",
            asset_id=page["assetId"],
            payload={"sourcePageAssetId": page["assetId"], "nodeIds": ["ghost"]},
        )
        self.assertEqual(ghost.status, 400)
        self.assertEqual(ghost.error_code, "invalid-target")
        no_source = self.post(
            self.project_id,
            "distill-candidate",
            asset_id=page["assetId"],
            payload={"nodeIds": ["title"]},
        )
        self.assertEqual(no_source.status, 400)


class ComponentCapabilityTest(ComponentApiTestCase):
    def test_a_read_capability_cannot_edit_or_publish_documents(self) -> None:
        component = self.create_component()
        read_only = self.capability(self.project_id, ["read"])
        readable = self.view("component", asset_id=component["assetId"], capability=read_only)
        self.assertEqual(readable.status, 200, readable.text)
        denied_edit = self.post(
            self.project_id,
            "component-update",
            asset_id=component["assetId"],
            payload={"definition": DEFINITION},
            capability=read_only,
        )
        self.assertEqual(denied_edit.status, 401)
        denied_publish = self.post(
            self.project_id,
            "component-publish",
            asset_id=component["assetId"],
            capability=read_only,
        )
        self.assertEqual(denied_publish.status, 401)
        denied_create = self.post(
            self.project_id,
            "components",
            payload={"name": "X", "definition": DEFINITION},
            capability=read_only,
        )
        self.assertEqual(denied_create.status, 401)
        page = self.create_page()
        denied_distill = self.post(
            self.project_id,
            "distill-candidate",
            asset_id=page["assetId"],
            payload={"sourcePageAssetId": page["assetId"], "nodeIds": ["title"]},
            capability=read_only,
        )
        self.assertEqual(denied_distill.status, 401)

    def test_a_capability_is_scoped_to_its_own_project(self) -> None:
        component = self.create_component()
        write_other = self.capability(self.other_id, ["read", "write"])
        response = self.view(
            "component", asset_id=component["assetId"], capability=write_other
        )
        self.assertEqual(response.status, 401)


if __name__ == "__main__":  # pragma: no cover - manual run
    unittest.main()
