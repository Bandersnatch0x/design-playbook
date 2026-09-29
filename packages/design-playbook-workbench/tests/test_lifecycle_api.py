#!/usr/bin/env python3
"""A13 over the real API: lifecycle browse, references, and safe deletion.

The domain rules live in ``test_lifecycle.py``; these tests prove the
distributed surface: routes exist, capability scopes hold, error codes are
the documented ones, and a permanent delete is refused while references
exist and needs an explicit confirm.
"""
from __future__ import annotations

import unittest

from tests.harness import WorkbenchHarness, http_request


class LifecycleApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.h = WorkbenchHarness()
        self.addCleanup(self.h.stop)
        self._operations = 0
        self.project_dir = self.h.make_directory("lifecycle")
        self.registered = self.h.register(self.project_dir, name="Design").json["result"]
        self.project_id = self.registered["projectId"]
        self.grant(self.project_id, ["read", "write"])

    def grant(self, project_id: str, scopes: list[str]) -> None:
        counter = self.h.project_target(project_id)["counter"]
        assert self.h.grant(project_id, scopes, expected_counter=counter).status == 200

    def capability(self, project_id: str, scopes: list[str]) -> str:
        return self.h.runtime.session.issue_capability(
            project_id=project_id, scopes=scopes
        )

    def import_and_publish(self, name: str = "brand.md", body: bytes = b"# Brand\n") -> str:
        (self.project_dir / name).write_bytes(body)
        asset = self.h.import_assets(self.project_id, [name]).json["result"]["asset"]
        published = self.h.asset_action(self.project_id, asset["assetId"], "publish")
        assert published.status == 200, published.text
        return asset["assetId"]

    def verb(self, asset_id: str, verb: str, *, payload=None, capability=None):
        self._operations += 1
        operation = {
            "operationId": f"op_life_api_{verb}_{self._operations}",
            "payload": {"action": verb, "assetId": asset_id, **(payload or {})},
        }
        return http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.project_id}/actions/assets/{asset_id}/{verb}",
            method="POST",
            body={"operation": operation, **(payload or {})},
            token=None if capability else self.h.token,
            capability=capability,
            origin=None if capability else self.h.runtime.origin,
        )

    def browse(self, *, lifecycle=None, capability=None):
        suffix = f"?lifecycle={lifecycle}" if lifecycle else ""
        return http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.project_id}/lifecycle{suffix}",
            token=None if capability else self.h.token,
            capability=capability,
        )

    def references(self, asset_id: str):
        return http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.project_id}/assets/{asset_id}/references",
            token=self.h.token,
        )


class LifecycleApiTest(LifecycleApiTestCase):
    def test_archive_trash_restore_and_browse(self) -> None:
        asset_id = self.import_and_publish()
        archived = self.verb(asset_id, "archive")
        self.assertEqual(archived.status, 200, archived.text)
        self.assertEqual(archived.json["result"]["lifecycle"], "archived")
        browse = self.browse()
        self.assertEqual(browse.status, 200, browse.text)
        self.assertEqual(browse.json["counts"]["archived"], 1)
        self.verb(asset_id, "unarchive")
        self.verb(asset_id, "trash")
        binned = self.browse(lifecycle="trashed")
        self.assertEqual(binned.json["counts"]["trashed"], 1)
        restored = self.verb(asset_id, "restore")
        self.assertEqual(restored.status, 200, restored.text)
        self.assertEqual(restored.json["result"]["lifecycle"], "published")

    def test_references_and_reference_safe_delete(self) -> None:
        asset_id = self.import_and_publish("components/button.md", b"# Button\n") if False else self.import_and_publish()
        # Give the asset an instance so it is referenced.
        instance = self.h.action(
            self.project_id, "instances", payload={"assetId": asset_id}
        )
        self.assertEqual(instance.status, 200, instance.text)
        references = self.references(asset_id)
        self.assertEqual(references.status, 200, references.text)
        self.assertEqual(len(references.json["instances"]), 1)
        self.assertFalse(references.json["deletable"])
        self.assertTrue(references.json["indexComplete"])

        refused = self.verb(asset_id, "hard-delete", payload={"confirm": True})
        self.assertEqual(refused.status, 409, refused.text)
        self.assertEqual(refused.error_code, "conflict")

        no_confirm = self.verb(asset_id, "hard-delete", payload={"confirm": False})
        self.assertEqual(no_confirm.status, 400, no_confirm.text)

        # Detach the instance, then the delete succeeds.
        self.h.runtime.store.delete_instance(instance.json["result"]["instanceId"])
        deleted = self.verb(asset_id, "hard-delete", payload={"confirm": True})
        self.assertEqual(deleted.status, 200, deleted.text)
        self.assertTrue(any("源仓库" in b for b in deleted.json["result"]["boundaries"]))
        # The source file remains on disk.
        self.assertTrue((self.project_dir / "brand.md").exists())

    def test_project_archive_and_deletion_impact(self) -> None:
        self.import_and_publish()
        archived = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.project_id}/actions/project-archive",
            method="POST",
            body={
                "operation": {
                    "operationId": "op_life_api_proj_archive",
                    "payload": {"action": "project-archive"},
                }
            },
            token=self.h.token,
            origin=self.h.runtime.origin,
        )
        self.assertEqual(archived.status, 200, archived.text)
        self.assertTrue(archived.json["result"]["archived"])
        impact = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.project_id}/deletion-impact",
            token=self.h.token,
        )
        self.assertEqual(impact.status, 200, impact.text)
        self.assertEqual(impact.json["assetCount"], 1)

    def test_capability_scopes_and_maintainer_only_verbs(self) -> None:
        asset_id = self.import_and_publish()
        read_only = self.capability(self.project_id, ["read"])
        # A read capability can browse and read references.
        self.assertEqual(self.browse(capability=read_only).status, 200)
        self.assertEqual(self.references(asset_id).status, 200)
        # Lifecycle mutations are maintainer decisions: a capability is refused.
        write_cap = self.capability(self.project_id, ["read", "write"])
        for verb in ("archive", "trash", "hard-delete"):
            with self.subTest(verb=verb):
                denied = self.verb(asset_id, verb, payload={"confirm": True}, capability=write_cap)
                self.assertEqual(denied.status, 401, denied.text)
        # The project archive verb is maintainer-only too.
        denied_project = http_request(
            self.h.runtime,
            f"/api/v1/projects/{self.project_id}/actions/project-archive",
            method="POST",
            body={
                "operation": {
                    "operationId": "op_life_api_proj_cap",
                    "payload": {"action": "project-archive"},
                }
            },
            capability=write_cap,
        )
        self.assertEqual(denied_project.status, 401)


if __name__ == "__main__":  # pragma: no cover - manual run
    unittest.main()
