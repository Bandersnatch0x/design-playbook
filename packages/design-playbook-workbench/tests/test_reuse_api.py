#!/usr/bin/env python3
"""A04/A05 over the real API: reuse, upgrade, and rollback through HTTP.

The domain rules are already covered directly; these tests exist to prove
the *distributed surface* behaves the same way -- the routes exist, the
capability scopes are enforced, and the error codes are the documented
ones.
"""
from __future__ import annotations

import json
import unittest


from tests.harness import WorkbenchHarness, http_request


class ReuseApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.h = WorkbenchHarness()
        self.addCleanup(self.h.stop)
        self.source_dir = self.h.make_directory("source")
        self.target_dir = self.h.make_directory("target")
        self.source = self.h.register(self.source_dir, name="Source").json["result"]
        self.target = self.h.register(self.target_dir, name="Target").json["result"]
        self.source_id = self.source["projectId"]
        self.target_id = self.target["projectId"]
        self.grant(self.source_id, ["read", "write"])
        self.grant(self.target_id, ["read", "write"])
        (self.source_dir / "brand.md").write_bytes(b"# Brand\n")
        self.asset = self.h.import_assets(self.source_id, ["brand.md"]).json["result"]["asset"]
        self.asset_id = self.asset["assetId"]
        published = self.h.asset_action(self.source_id, self.asset_id, "publish")
        assert published.status == 200, published.text
        self.instance = self.h.action(
            self.source_id,
            "instances",
            payload={"assetId": self.asset_id},
        )
        assert self.instance.status == 200, self.instance.text
        self.instance_id = self.instance.json["result"]["instanceId"]

    def grant(self, project_id: str, scopes: list[str]) -> None:
        counter = self.h.project_target(project_id)["counter"]
        response = self.h.grant(project_id, scopes, expected_counter=counter)
        assert response.status == 200, response.text

    def capability(self, project_id: str, scopes: list[str]) -> str:
        return self.h.runtime.session.issue_capability(
            project_id=project_id, scopes=scopes
        )


class ReuseReadApiTest(ReuseApiTestCase):
    def test_instances_history_and_upgrade_plan_are_readable(self) -> None:
        listing = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.source_id}/instances",
            token=self.h.token,
        )
        self.assertEqual(listing.status, 200, listing.text)
        self.assertEqual(len(listing.json["instances"]), 1)
        self.assertEqual(listing.json["instances"][0]["assetId"], self.asset_id)

        history = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.source_id}/assets/{self.asset_id}/history",
            token=self.h.token,
        )
        self.assertEqual(history.status, 200, history.text)
        self.assertEqual(len(history.json["revisions"]), 1)
        self.assertEqual(history.json["lineage"], [])

        plan = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.source_id}/assets/{self.asset_id}/upgrade-plan",
            token=self.h.token,
        )
        self.assertEqual(plan.status, 200, plan.text)
        self.assertEqual(plan.json["candidates"], [])
        self.assertIn("整组原子更新", plan.json["notes"])

    def test_reuse_plan_names_the_closure_and_needs_a_target(self) -> None:
        response = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.source_id}/assets/{self.asset_id}"
            f"/reuse-plan?targetProjectId={self.target_id}&mode=copy",
            token=self.h.token,
        )
        self.assertEqual(response.status, 200, response.text)
        self.assertEqual(response.json["source"]["assetId"], self.asset_id)
        self.assertEqual(response.json["target"]["projectId"], self.target_id)
        self.assertEqual(
            [entry["path"] for entry in response.json["manifest"]], ["brand.md"]
        )
        missing = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.source_id}/assets/{self.asset_id}/reuse-plan",
            token=self.h.token,
        )
        self.assertEqual(missing.status, 400)
        self.assertEqual(missing.error_code, "invalid-input")

    def test_unknown_views_and_foreign_assets_are_refused(self) -> None:
        unknown = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.source_id}/assets/{self.asset_id}/nonsense",
            token=self.h.token,
        )
        self.assertEqual(unknown.status, 404)
        foreign = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.target_id}/assets/{self.asset_id}",
            token=self.h.token,
        )
        self.assertEqual(foreign.status, 400)
        self.assertEqual(foreign.error_code, "invalid-target")


class ReuseWriteApiTest(ReuseApiTestCase):
    def test_cross_project_import_then_upgrade_and_rollback(self) -> None:
        imported = self.h.asset_action_import_closure(
            self.source_id,
            self.asset_id,
            target_project_id=self.target_id,
            mode="copy",
        )
        self.assertEqual(imported.status, 200, imported.text)
        local_asset_id = imported.json["result"]["assetId"]
        self.assertNotEqual(local_asset_id, self.asset_id)
        self.assertEqual(
            imported.json["result"]["source"]["assetId"], self.asset_id
        )

        # A local instance in the target project, then a new source revision.
        created = self.h.action(
            self.target_id, "instances", payload={"assetId": local_asset_id}
        )
        self.assertEqual(created.status, 200, created.text)
        local_instance = created.json["result"]["instanceId"]

        (self.source_dir / "brand.md").write_bytes(b"# Brand v2\n")
        self.assertEqual(
            self.h.asset_action(self.source_id, self.asset_id, "refresh-draft").status,
            200,
        )
        self.assertEqual(
            self.h.asset_action(self.source_id, self.asset_id, "publish").status, 200
        )
        # The imported copy is a snapshot: it keeps pointing at revision 1 and
        # reports no upgrade candidates of its own.
        local_plan = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.target_id}/assets/{local_asset_id}/upgrade-plan",
            token=self.h.token,
        )
        self.assertEqual(local_plan.status, 200, local_plan.text)
        self.assertEqual(local_plan.json["candidates"], [])

        # The *source* instance can move to the new revision.
        upgrade = self.h.asset_action(
            self.source_id,
            self.asset_id,
            "upgrade",
            payload={"instanceIds": [self.instance_id]},
        )
        self.assertEqual(upgrade.status, 200, upgrade.text)
        self.assertEqual(
            upgrade.json["result"]["updatedInstanceIds"], [self.instance_id]
        )
        rollback = self.h.asset_action(
            self.source_id,
            self.asset_id,
            "rollback",
            payload={
                "instanceIds": [self.instance_id],
                "toRevisionId": self._revision_id(self.source_id, self.asset_id, 1),
            },
        )
        self.assertEqual(rollback.status, 200, rollback.text)
        history = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.source_id}/assets/{self.asset_id}/history",
            token=self.h.token,
        )
        kinds = [record["kind"] for record in history.json["records"]]
        self.assertEqual(kinds, ["upgrade", "rollback"])
        self.assertNotEqual(local_instance, self.instance_id)

    def _revision_id(self, project_id: str, asset_id: str, number: int) -> str:
        history = http_request(
            self.h.runtime,
            f"/api/v1/projects/{project_id}/assets/{asset_id}/history",
            token=self.h.token,
        )
        for row in history.json["revisions"]:
            if row["revisionNumber"] == number:
                return row["revisionId"]
        raise AssertionError("revision not found")

    def test_derive_copy_and_reference_through_the_api(self) -> None:
        derived = self.h.asset_action(self.source_id, self.asset_id, "derive")
        self.assertEqual(derived.status, 200, derived.text)
        copied = self.h.asset_action(self.source_id, self.asset_id, "copy")
        self.assertEqual(copied.status, 200, copied.text)
        reference = self.h.asset_action(self.source_id, self.asset_id, "reference")
        self.assertEqual(reference.status, 200, reference.text)
        self.assertNotEqual(
            derived.json["result"]["assetId"], copied.json["result"]["assetId"]
        )
        self.assertEqual(reference.json["result"]["assetId"], self.asset_id)
        history = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.source_id}/assets/{derived.json['result']['assetId']}/history",
            token=self.h.token,
        )
        self.assertEqual(
            [row["relation"] for row in history.json["lineage"]], ["derived-from"]
        )

    def test_publish_with_dependencies_reports_missing_dependencies(self) -> None:
        response = self.h.asset_action(
            self.source_id,
            self.asset_id,
            "publish-with-deps",
            payload={
                "dependencies": [
                    {
                        "assetId": self.asset_id,
                        "revisionId": "00000000-0000-4000-8000-000000000000",
                    }
                ]
            },
        )
        self.assertEqual(response.status, 422)
        self.assertEqual(response.error_code, "missing-dependency")

    def test_conflicting_upgrade_is_refused_without_changing_anything(self) -> None:
        # A target revision that declares no public parameters conflicts with
        # an instance that carries overrides.
        first = self._revision_id(self.source_id, self.asset_id, 1)
        self.h.runtime.store.connection.execute(
            "UPDATE revisions SET origin_json = ? WHERE revision_id = ?",
            (json.dumps({"publicParams": [{"name": "label"}]}), first),
        )
        with_override = self.h.action(
            self.source_id,
            "instances",
            payload={"assetId": self.asset_id, "revisionId": first, "overrides": {"label": "A"}},
        )
        self.assertEqual(with_override.status, 200, with_override.text)
        (self.source_dir / "brand.md").write_bytes(b"# v2\n")
        self.assertEqual(
            self.h.asset_action(self.source_id, self.asset_id, "refresh-draft").status,
            200,
        )
        self.assertEqual(
            self.h.asset_action(self.source_id, self.asset_id, "publish").status, 200
        )
        refused = self.h.asset_action(
            self.source_id,
            self.asset_id,
            "upgrade",
            payload={"instanceIds": [with_override.json["result"]["instanceId"]]},
        )
        self.assertEqual(refused.status, 409, refused.text)
        self.assertEqual(refused.error_code, "conflict")
        listed = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.source_id}/instances",
            token=self.h.token,
        )
        untouched = {
            row["instanceId"]: row["revisionId"] for row in listed.json["instances"]
        }
        self.assertEqual(
            untouched[with_override.json["result"]["instanceId"]], first
        )


class ReuseCapabilityTest(ReuseApiTestCase):
    def test_a_read_capability_cannot_import_or_upgrade(self) -> None:
        read_only = self.capability(self.source_id, ["read"])
        listing = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.source_id}/instances",
            capability=read_only,
        )
        self.assertEqual(listing.status, 200, listing.text)
        denied = self.h.asset_action(
            self.source_id,
            self.asset_id,
            "upgrade",
            payload={"instanceIds": [self.instance_id]},
            capability=read_only,
        )
        self.assertEqual(denied.status, 401)

    def test_a_write_capability_is_scoped_to_its_own_project(self) -> None:
        write_capability = self.capability(self.target_id, ["read", "write"])
        # The closure import touches two projects: a capability for the
        # target alone cannot name a source it does not own.
        response = self.h.asset_action_import_closure(
            self.source_id,
            self.asset_id,
            target_project_id=self.target_id,
            mode="copy",
            capability=write_capability,
        )
        self.assertEqual(response.status, 401)

    def test_capabilities_cannot_publish_into_a_foreign_project(self) -> None:
        capability = self.capability(self.source_id, ["read", "write"])
        response = self.h.asset_action(
            self.target_id,
            self.asset_id,
            "publish",
            capability=capability,
        )
        self.assertEqual(response.status, 401)
        self.assertIn("unauthorized", response.text)


if __name__ == "__main__":  # pragma: no cover - manual run
    unittest.main()
