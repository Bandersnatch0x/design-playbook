#!/usr/bin/env python3
"""A04/A05: immutable revisions, reuse identity, and controlled upgrades.

The two properties under test are that nothing silently becomes "latest"
and that reuse is an explicit, closed, resolvable copy. Every scenario uses
real temporary directories and the real domain services.
"""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from design_playbook_workbench.assets import AssetService
from design_playbook_workbench.blobs import BlobStore
from design_playbook_workbench.errors import (
    CONFLICT,
    CORRUPT_CONTENT,
    INVALID_INPUT,
    INVALID_TARGET,
    LIMIT_EXCEEDED,
    MISSING_DEPENDENCY,
    WorkbenchError,
)
from design_playbook_workbench.reuse import ReuseService
from design_playbook_workbench.service import Operation, WorkbenchService
from design_playbook_workbench.store import Store, WorkbenchDataDirectory


class ReuseTestCase(unittest.TestCase):
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
            store=self.store,
            service=self.service,
            assets=self.assets,
            blobs=self.blobs,
        )
        self._operations = 0
        self.source = self._project("source")
        self.target = self._project("target")
        self.source_id = self.source["projectId"]
        self.target_id = self.target["projectId"]

    def tearDown(self) -> None:
        self.store.close()
        self._tmp.cleanup()

    def operation(self, payload: dict, *, expected: int | None = None, operation_id: str | None = None):
        if operation_id is None:
            self._operations += 1
            operation_id = f"op_reuse_{self._operations:08d}"
        return Operation(
            operation_id=operation_id, payload=payload, expected_counter=expected
        )

    def _project(self, name: str) -> dict:
        path = self.base / name
        path.mkdir()
        candidate = self.service.probe_folder(path)
        return self.service.register_project(
            path=candidate.canonical_path,
            candidate_id=candidate.candidate_id,
            name=name.title(),
            operation=self.operation({"action": "register-project"}),
        )["result"]

    def grant(self, project_id: str, scopes: list[str]) -> None:
        counter = int(self.store.project(project_id)["counter"])
        self.service.set_grants(
            project_id,
            scopes=scopes,
            operation=self.operation({"scopes": scopes}, expected=counter),
        )

    def write(self, project: str, relative: str, text: str) -> None:
        path = self.base / project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))

    def import_and_publish(
        self, project: str, project_id: str, relative: str, *, dependencies=None
    ) -> dict:
        self.grant(project_id, ["read", "write"])
        self.write(project, relative, f"# {relative}\n")
        asset = self.assets.import_selection(
            project_id,
            selections=[relative],
            operation=self.operation({"selections": [relative]}),
        )["result"]["asset"]
        self.assets.publish_revision(
            project_id, asset["assetId"], operation=self.operation({"publish": 1})
        )
        if dependencies is not None:
            self.reuse.publish_with_dependencies(
                project_id,
                asset["assetId"],
                dependencies=dependencies,
                operation=self.operation({"publish-deps": 1}),
            )
        return self.assets.asset_detail(project_id, asset["assetId"])["asset"]


class RevisionImmutabilityTest(ReuseTestCase):
    def test_published_revisions_are_never_edited_and_ids_are_stable(self) -> None:
        asset = self.import_and_publish("source", self.source_id, "spec.md")
        asset_id = asset["assetId"]
        first = self.store.latest_revision(asset_id)
        # A rename of the asset does not change the asset id or the revision.
        self.service.rename_project(
            self.source_id,
            name="Renamed",
            operation=self.operation(
                {"name": "Renamed"},
                expected=int(self.store.project(self.source_id)["counter"]),
            ),
        )
        self.write("source", "spec.md", "# changed on disk\n")
        self.assets.refresh_draft(
            self.source_id, asset_id, operation=self.operation({"refresh": 1})
        )
        self.assets.publish_revision(
            self.source_id, asset_id, operation=self.operation({"publish": 2})
        )
        revisions = self.store.asset_revisions(asset_id)
        self.assertEqual([row["revision_number"] for row in revisions], [1, 2])
        self.assertEqual(revisions[0]["revision_id"], first["revision_id"])
        self.assertEqual(revisions[0]["content_hash"], first["content_hash"])
        self.assertNotEqual(revisions[0]["content_hash"], revisions[1]["content_hash"])
        self.assertEqual(self.store.asset(asset_id)["asset_id"], asset_id)

    def test_publishing_never_re_reads_the_source_tree_on_its_own(self) -> None:
        """The repository is not the authority for what an asset contains.

        Editing the file and publishing again must produce a *new revision
        of the same snapshot*; only an explicit draft refresh brings the
        changed bytes in.
        """
        asset = self.import_and_publish("source", self.source_id, "spec.md")
        asset_id = asset["assetId"]
        first = self.store.latest_revision(asset_id)
        self.write("source", "spec.md", "# silently changed on disk\n")
        self.assets.publish_revision(
            self.source_id, asset_id, operation=self.operation({"publish": "no-refresh"})
        )
        revisions = self.store.asset_revisions(asset_id)
        self.assertEqual(len(revisions), 2)
        self.assertNotEqual(revisions[0]["revision_id"], revisions[1]["revision_id"])
        self.assertEqual(revisions[0]["content_hash"], revisions[1]["content_hash"])
        self.assertEqual(revisions[1]["content_hash"], first["content_hash"])
        # The draft still holds the snapshot it was imported with, and the
        # refreshed draft is what changes it.
        refreshed = self.assets.refresh_draft(
            self.source_id, asset_id, operation=self.operation({"refresh": "after"})
        )["result"]
        self.assertNotEqual(
            refreshed["manifest"][0]["contentHash"], first["content_hash"]
        )

    def test_refreshing_a_draft_reports_a_source_that_disappeared(self) -> None:
        asset = self.import_and_publish("source", self.source_id, "spec.md")
        (self.base / "source" / "spec.md").unlink()
        with self.assertRaises(WorkbenchError) as caught:
            self.assets.refresh_draft(
                self.source_id, asset["assetId"], operation=self.operation({"refresh": "gone"})
            )
        self.assertEqual(caught.exception.code, INVALID_TARGET)

    def test_oversized_publish_and_corrupt_blob_are_refused(self) -> None:
        asset = self.import_and_publish("source", self.source_id, "spec.md")
        asset_id = asset["assetId"]
        revision = self.store.latest_revision(asset_id)
        manifest = json.loads(revision["manifest_json"])
        self.blobs.path_for(manifest[0]["contentHash"]).write_bytes(b"tampered")
        with self.assertRaises(WorkbenchError) as caught:
            self.assets.publish_revision(
                self.source_id, asset_id, operation=self.operation({"publish": 3})
            )
        self.assertEqual(caught.exception.code, CORRUPT_CONTENT)

    def test_stale_counter_and_reused_operation_ids_behave_as_specified(self) -> None:
        asset = self.import_and_publish("source", self.source_id, "spec.md")
        asset_id = asset["assetId"]
        operation = self.operation(
            {"publish": asset_id}, operation_id="op_publish_same_1"
        )
        first = self.assets.publish_revision(
            self.source_id, asset_id, operation=operation
        )
        replay = self.assets.publish_revision(
            self.source_id, asset_id, operation=operation
        )
        self.assertFalse(first["replayed"])
        self.assertTrue(replay["replayed"])
        self.assertEqual(len(self.store.asset_revisions(asset_id)), 2)
        with self.assertRaises(WorkbenchError) as caught:
            self.assets.publish_revision(
                self.source_id,
                asset_id,
                operation=self.operation(
                    {"publish": "different"}, operation_id="op_publish_same_1"
                ),
            )
        self.assertEqual(caught.exception.code, CONFLICT)


class DependencyClosureTest(ReuseTestCase):
    def test_dependencies_must_resolve_inside_the_project(self) -> None:
        tokens = self.import_and_publish("source", self.source_id, "tokens/brand.json")
        with self.assertRaises(WorkbenchError) as caught:
            self.import_and_publish(
                "source",
                self.source_id,
                "components/button.md",
                dependencies=[
                    {
                        "assetId": tokens["assetId"],
                        "revisionId": "00000000-0000-4000-8000-000000000000",
                    }
                ],
            )
        self.assertEqual(caught.exception.code, MISSING_DEPENDENCY)

    def test_a_dependency_cycle_is_refused(self) -> None:
        first = self.import_and_publish("source", self.source_id, "a.md")
        second = self.import_and_publish("source", self.source_id, "b.md")
        first_revision = self.store.latest_revision(first["assetId"])
        second_revision = self.store.latest_revision(second["assetId"])
        self.store.insert_dependencies(
            revision_id=first_revision["revision_id"],
            dependencies=[
                {
                    "assetId": second["assetId"],
                    "revisionId": second_revision["revision_id"],
                }
            ],
            now="2026-09-26T12:00:00Z",
        )
        # Closing the loop must be refused, and nothing new is published.
        with self.assertRaises(WorkbenchError) as caught:
            self.reuse.publish_with_dependencies(
                self.source_id,
                second["assetId"],
                dependencies=[
                    {
                        "assetId": first["assetId"],
                        "revisionId": first_revision["revision_id"],
                    }
                ],
                operation=self.operation({"publish-deps": "cycle"}),
            )
        self.assertEqual(caught.exception.code, MISSING_DEPENDENCY)
        self.assertEqual(len(self.store.asset_revisions(second["assetId"])), 1)

    def test_a_valid_dependency_publishes_with_its_closure(self) -> None:
        tokens = self.import_and_publish("source", self.source_id, "tokens/brand.json")
        tokens_revision = self.store.latest_revision(tokens["assetId"])
        component = self.import_and_publish(
            "source",
            self.source_id,
            "components/button.md",
            dependencies=[
                {
                    "assetId": tokens["assetId"],
                    "revisionId": tokens_revision["revision_id"],
                }
            ],
        )
        component_revision = self.store.latest_revision(component["assetId"])
        self.assertEqual(
            [row["depends_on_asset_id"] for row in self.store.dependencies(component_revision["revision_id"])],
            [tokens["assetId"]],
        )
        closure = self.reuse.dependency_closure(
            self.source_id, component_revision["revision_id"]
        )
        self.assertEqual(
            [entry["assetId"] for entry in closure], [tokens["assetId"]]
        )


class LineageTest(ReuseTestCase):
    def test_reference_derive_and_copy_have_distinct_identity_rules(self) -> None:
        asset = self.import_and_publish("source", self.source_id, "brand.md")
        revision = self.store.latest_revision(asset["assetId"])

        reference = self.reuse.derive_or_copy(
            self.source_id,
            asset["assetId"],
            mode="reference",
            operation=self.operation({"mode": "reference"}),
        )["result"]
        # A reference keeps the same asset identity: only an instance exists.
        self.assertEqual(reference["assetId"], asset["assetId"])
        self.assertEqual(reference["revisionId"], revision["revision_id"])

        derived = self.reuse.derive_or_copy(
            self.source_id,
            asset["assetId"],
            mode="derive",
            operation=self.operation({"mode": "derive"}),
        )["result"]
        copied = self.reuse.derive_or_copy(
            self.source_id,
            asset["assetId"],
            mode="copy",
            operation=self.operation({"mode": "copy"}),
        )["result"]
        self.assertNotEqual(derived["assetId"], asset["assetId"])
        self.assertNotEqual(copied["assetId"], asset["assetId"])
        self.assertNotEqual(derived["assetId"], copied["assetId"])
        self.assertEqual(
            [row["relation"] for row in self.store.lineage(derived["assetId"])],
            ["derived-from"],
        )
        self.assertEqual(
            [row["relation"] for row in self.store.lineage(copied["assetId"])],
            ["copied-from"],
        )

    def test_a_copy_inherits_content_but_no_approval(self) -> None:
        asset = self.import_and_publish("source", self.source_id, "brand.md")
        reference_revision = self.store.latest_revision(asset["assetId"])
        # Pretend the source revision carried a verified capability: the
        # copy must start with an empty verification list regardless.
        self.store.connection.execute(
            "UPDATE revisions SET verified_json = ? WHERE revision_id = ?",
            (json.dumps([{"verdict": "pass"}]), reference_revision["revision_id"]),
        )
        copied = self.reuse.derive_or_copy(
            self.source_id,
            asset["assetId"],
            mode="copy",
            operation=self.operation({"mode": "copy"}),
        )["result"]
        copied_revision = self.store.latest_revision(copied["assetId"])
        self.assertEqual(json.loads(copied_revision["verified_json"]), [])
        self.assertEqual(
            copied_revision["content_hash"], reference_revision["content_hash"]
        )

    def test_deriving_from_a_foreign_project_asset_is_refused(self) -> None:
        asset = self.import_and_publish("source", self.source_id, "brand.md")
        self.grant(self.target_id, ["read", "write"])
        with self.assertRaises(WorkbenchError) as caught:
            self.reuse.derive_or_copy(
                self.target_id,
                asset["assetId"],
                mode="copy",
                operation=self.operation({"mode": "copy"}),
            )
        self.assertEqual(caught.exception.code, INVALID_TARGET)


class CrossProjectReuseTest(ReuseTestCase):
    def test_reuse_plan_lists_only_the_explicit_closure(self) -> None:
        tokens = self.import_and_publish("source", self.source_id, "tokens/brand.json")
        self.grant(self.target_id, ["read"])
        tokens_revision = self.store.latest_revision(tokens["assetId"])
        component = self.import_and_publish(
            "source",
            self.source_id,
            "components/button.md",
            dependencies=[
                {
                    "assetId": tokens["assetId"],
                    "revisionId": tokens_revision["revision_id"],
                }
            ],
        )
        self.write("source", "private/notes.md", "# private\n")
        private = self.assets.import_selection(
            self.source_id,
            selections=["private/notes.md"],
            operation=self.operation({"selections": ["private"]}),
        )["result"]["asset"]

        plan = self.reuse.reuse_plan(
            self.source_id,
            source_asset_id=component["assetId"],
            source_revision_id=None,
            mode="copy",
            target_project_id=self.target_id,
        )
        self.assertEqual(plan["source"]["assetId"], component["assetId"])
        self.assertEqual(
            [entry["assetId"] for entry in plan["dependencies"]], [tokens["assetId"]]
        )
        self.assertEqual([entry["path"] for entry in plan["manifest"]], ["components/button.md"])
        for excluded in ("其他画布内容", "运行日志与证据", "源项目私有路径"):
            self.assertIn(excluded, plan["excluded"])
        self.assertNotIn(private["assetId"], json.dumps(plan))

    def test_imported_closure_resolves_after_the_source_is_disconnected(self) -> None:
        asset = self.import_and_publish("source", self.source_id, "brand.md")
        self.grant(self.target_id, ["read", "write"])
        imported = self.reuse.import_closure(
            self.source_id,
            source_asset_id=asset["assetId"],
            source_revision_id=None,
            mode="copy",
            target_project_id=self.target_id,
            operation=self.operation({"import-closure": 1}),
        )["result"]
        local_asset_id = imported["assetId"]
        self.assertNotEqual(local_asset_id, asset["assetId"])
        self.assertEqual(
            [entry["path"] for entry in imported["manifest"]], ["brand.md"]
        )
        # The imported copy is resolvable in the target project ...
        detail = self.assets.asset_detail(self.target_id, local_asset_id)["asset"]
        self.assertEqual(detail["revisionNumber"], 1)
        instance = self.reuse.create_instance(
            self.target_id,
            local_asset_id,
            operation=self.operation({"instance": 1}),
        )["result"]
        self.assertEqual(instance["assetId"], local_asset_id)

        # ... even after the source project directory disappears entirely.
        shutil.rmtree(self.base / "source")
        target_view = self.service.project_target(self.target_id)["connectionState"]
        self.assertEqual(target_view, "connected")
        self.assertEqual(
            self.assets.asset_detail(self.target_id, local_asset_id)["asset"]["name"],
            "brand.md",
        )
        self.assertEqual(
            len(self.reuse.list_instances(self.target_id)["instances"]), 1
        )
        # The source project reports disconnected, but nothing leaks back.
        self.assertEqual(
            self.service.project_target(self.source_id)["connectionState"],
            "disconnected",
        )

    def test_import_refuses_unknown_sources_and_missing_blobs(self) -> None:
        asset = self.import_and_publish("source", self.source_id, "brand.md")
        self.grant(self.target_id, ["read", "write"])
        with self.assertRaises(WorkbenchError) as caught:
            self.reuse.import_closure(
                self.source_id,
                source_asset_id="00000000-0000-4000-8000-000000000000",
                source_revision_id=None,
                mode="copy",
                target_project_id=self.target_id,
                operation=self.operation({"import-closure": 2}),
            )
        self.assertEqual(caught.exception.code, INVALID_TARGET)

        revision = self.store.latest_revision(asset["assetId"])
        manifest = json.loads(revision["manifest_json"])
        self.blobs.path_for(manifest[0]["contentHash"]).unlink()
        with self.assertRaises(WorkbenchError) as caught:
            self.reuse.reuse_plan(
                self.source_id,
                source_asset_id=asset["assetId"],
                source_revision_id=None,
                mode="copy",
                target_project_id=self.target_id,
            )
        self.assertEqual(caught.exception.code, CORRUPT_CONTENT)


class UpgradeTest(ReuseTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.asset = self.import_and_publish("source", self.source_id, "brand.md")
        self.asset_id = self.asset["assetId"]
        self.grant(self.source_id, ["read", "write"])

    def _new_revision(self, text: str) -> dict:
        self.write("source", "brand.md", text)
        self.assets.refresh_draft(
            self.source_id, self.asset_id, operation=self.operation({"refresh": text[:8]})
        )
        self.assets.publish_revision(
            self.source_id, self.asset_id, operation=self.operation({"publish": text[:8]})
        )
        return self.store.latest_revision(self.asset_id)

    def test_upgrade_is_per_instance_and_never_automatic(self) -> None:
        first = self.store.latest_revision(self.asset_id)
        older = self.reuse.create_instance(
            self.source_id,
            self.asset_id,
            revision_id=first["revision_id"],
            operation=self.operation({"instance": "older"}),
        )["result"]
        second = self._new_revision("# v2\n")
        newer = self.reuse.create_instance(
            self.source_id,
            self.asset_id,
            revision_id=second["revision_id"],
            operation=self.operation({"instance": "newer"}),
        )["result"]

        # Publishing changed nothing that already existed.
        self.assertEqual(
            self.reuse.list_instances(self.source_id)["instances"][0]["revisionId"],
            first["revision_id"],
        )
        plan = self.reuse.upgrade_plan(self.source_id, self.asset_id)
        candidates = {item["fromRevisionId"]: item for item in plan["candidates"]}
        self.assertEqual(candidates[first["revision_id"]]["instanceIds"], [older["instanceId"]])
        self.assertTrue(candidates[first["revision_id"]]["upgradable"])

        outcome = self.reuse.upgrade_instances(
            self.source_id,
            self.asset_id,
            instance_ids=[older["instanceId"]],
            operation=self.operation({"upgrade": 1}),
        )["result"]
        self.assertEqual(outcome["updatedInstanceIds"], [older["instanceId"]])
        self.assertEqual(outcome["untouchedInstanceIds"], [])
        by_id = {row["instanceId"]: row for row in outcome["instances"]}
        self.assertEqual(by_id[older["instanceId"]]["revisionId"], second["revision_id"])
        self.assertEqual(by_id[newer["instanceId"]]["revisionId"], second["revision_id"])

        # The second instance was already on the target revision, so the
        # upgrade plan no longer offers it.
        plan_again = self.reuse.upgrade_plan(self.source_id, self.asset_id)
        self.assertEqual(plan_again["candidates"], [])

    def test_an_unselected_instance_stays_put(self) -> None:
        first = self.store.latest_revision(self.asset_id)
        keep = self.reuse.create_instance(
            self.source_id,
            self.asset_id,
            revision_id=first["revision_id"],
            operation=self.operation({"instance": "keep"}),
        )["result"]
        other = self.reuse.create_instance(
            self.source_id,
            self.asset_id,
            revision_id=first["revision_id"],
            operation=self.operation({"instance": "other"}),
        )["result"]
        second = self._new_revision("# v2\n")
        outcome = self.reuse.upgrade_instances(
            self.source_id,
            self.asset_id,
            instance_ids=[other["instanceId"]],
            to_revision_id=second["revision_id"],
            operation=self.operation({"upgrade": 2}),
        )["result"]
        by_id = {row["instanceId"]: row for row in outcome["instances"]}
        self.assertEqual(by_id[keep["instanceId"]]["revisionId"], first["revision_id"])
        self.assertEqual(by_id[other["instanceId"]]["revisionId"], second["revision_id"])
        self.assertEqual(outcome["untouchedInstanceIds"], [keep["instanceId"]])

    def test_a_conflicting_override_blocks_the_whole_selected_group(self) -> None:
        first = self.store.latest_revision(self.asset_id)
        self.store.connection.execute(
            "UPDATE revisions SET origin_json = ? WHERE revision_id = ?",
            (
                json.dumps({"publicParams": [{"name": "label"}]}),
                first["revision_id"],
            ),
        )
        good = self.reuse.create_instance(
            self.source_id,
            self.asset_id,
            revision_id=first["revision_id"],
            overrides={"label": "A"},
            operation=self.operation({"instance": "good"}),
        )["result"]
        # A target revision that no longer declares the overridden parameter
        # makes the upgrade conflicting for every selected instance.
        second = self._new_revision("# v2\n")
        self.store.connection.execute(
            "UPDATE revisions SET origin_json = '{}' WHERE revision_id = ?",
            (second["revision_id"],),
        )
        with self.assertRaises(WorkbenchError) as caught:
            self.reuse.upgrade_instances(
                self.source_id,
                self.asset_id,
                instance_ids=[good["instanceId"]],
                to_revision_id=second["revision_id"],
                operation=self.operation({"upgrade": 3}),
            )
        self.assertEqual(caught.exception.code, CONFLICT)
        plan = self.reuse.upgrade_plan(
            self.source_id, self.asset_id, to_revision_id=second["revision_id"]
        )
        candidate = plan["candidates"][0]
        self.assertFalse(candidate["upgradable"])
        self.assertEqual(candidate["conflicts"][0]["kind"], "override-unsupported")
        # Nothing changed.
        self.assertEqual(
            self.reuse.list_instances(self.source_id)["instances"][0]["revisionId"],
            first["revision_id"],
        )

    def test_rollback_restores_an_older_revision_as_a_new_record(self) -> None:
        first = self.store.latest_revision(self.asset_id)
        instance = self.reuse.create_instance(
            self.source_id,
            self.asset_id,
            revision_id=first["revision_id"],
            operation=self.operation({"instance": "rb"}),
        )["result"]
        second = self._new_revision("# v2\n")
        self.reuse.upgrade_instances(
            self.source_id,
            self.asset_id,
            instance_ids=[instance["instanceId"]],
            to_revision_id=second["revision_id"],
            operation=self.operation({"upgrade": 4}),
        )
        outcome = self.reuse.rollback_instances(
            self.source_id,
            self.asset_id,
            instance_ids=[instance["instanceId"]],
            to_revision_id=first["revision_id"],
            operation=self.operation({"rollback": 1}),
        )["result"]
        self.assertEqual(outcome["restoredRevisionId"], first["revision_id"])
        # History is additive: the upgrade record survives alongside it.
        history = self.reuse.asset_history(self.source_id, self.asset_id)
        kinds = [record["kind"] for record in history["records"]]
        self.assertEqual(kinds, ["upgrade", "rollback"])
        self.assertEqual(
            [row["revisionNumber"] for row in history["revisions"]], [1, 2]
        )

    def test_rollback_to_unknown_or_damaged_content_is_reported(self) -> None:
        first = self.store.latest_revision(self.asset_id)
        instance = self.reuse.create_instance(
            self.source_id,
            self.asset_id,
            revision_id=first["revision_id"],
            operation=self.operation({"instance": "rb2"}),
        )["result"]
        with self.assertRaises(WorkbenchError) as caught:
            self.reuse.rollback_instances(
                self.source_id,
                self.asset_id,
                instance_ids=[instance["instanceId"]],
                to_revision_id="00000000-0000-4000-8000-000000000000",
                operation=self.operation({"rollback": 2}),
            )
        self.assertEqual(caught.exception.code, CORRUPT_CONTENT)

        manifest = json.loads(first["manifest_json"])
        self.blobs.path_for(manifest[0]["contentHash"]).unlink()
        with self.assertRaises(WorkbenchError) as caught:
            self.reuse.rollback_instances(
                self.source_id,
                self.asset_id,
                instance_ids=[instance["instanceId"]],
                to_revision_id=first["revision_id"],
                operation=self.operation({"rollback": 3}),
            )
        self.assertEqual(caught.exception.code, CORRUPT_CONTENT)

    def test_instance_overrides_must_name_declared_public_params(self) -> None:
        first = self.store.latest_revision(self.asset_id)
        self.store.connection.execute(
            "UPDATE revisions SET origin_json = ? WHERE revision_id = ?",
            (
                json.dumps({"publicParams": [{"name": "label"}]}),
                first["revision_id"],
            ),
        )
        with self.assertRaises(WorkbenchError) as caught:
            self.reuse.create_instance(
                self.source_id,
                self.asset_id,
                revision_id=first["revision_id"],
                overrides={"not-declared": 1},
                operation=self.operation({"instance": "bad"}),
            )
        self.assertEqual(caught.exception.code, INVALID_INPUT)
        accepted = self.reuse.create_instance(
            self.source_id,
            self.asset_id,
            revision_id=first["revision_id"],
            overrides={"label": "ok"},
            operation=self.operation({"instance": "good2"}),
        )["result"]
        self.assertEqual(accepted["overrides"], {"label": "ok"})

    def test_upgrade_and_rollback_are_idempotent_and_require_membership(self) -> None:
        first = self.store.latest_revision(self.asset_id)
        instance = self.reuse.create_instance(
            self.source_id,
            self.asset_id,
            revision_id=first["revision_id"],
            operation=self.operation({"instance": "idem"}),
        )["result"]
        second = self._new_revision("# v2\n")
        operation = self.operation({"upgrade": "idem"}, operation_id="op_upgrade_idem_1")
        first_run = self.reuse.upgrade_instances(
            self.source_id,
            self.asset_id,
            instance_ids=[instance["instanceId"]],
            to_revision_id=second["revision_id"],
            operation=operation,
        )
        replay = self.reuse.upgrade_instances(
            self.source_id,
            self.asset_id,
            instance_ids=[instance["instanceId"]],
            to_revision_id=second["revision_id"],
            operation=operation,
        )
        self.assertFalse(first_run["replayed"])
        self.assertTrue(replay["replayed"])
        with self.assertRaises(WorkbenchError) as caught:
            self.reuse.upgrade_instances(
                self.source_id,
                self.asset_id,
                instance_ids=["00000000-0000-4000-8000-000000000000"],
                to_revision_id=second["revision_id"],
                operation=self.operation({"upgrade": "unknown"}),
            )
        self.assertEqual(caught.exception.code, INVALID_TARGET)


class ClosureLimitTest(ReuseTestCase):
    def test_declaring_too_many_dependencies_is_refused(self) -> None:
        asset = self.import_and_publish("source", self.source_id, "brand.md")
        revision = self.store.latest_revision(asset["assetId"])
        oversized = [
            {"assetId": asset["assetId"], "revisionId": revision["revision_id"]}
            for _ in range(1)
        ]
        from design_playbook_workbench import reuse as module

        with mock.patch.object(module, "MAX_CLOSURE_REVISIONS", 0):
            with self.assertRaises(WorkbenchError) as caught:
                self.reuse.publish_with_dependencies(
                    self.source_id,
                    asset["assetId"],
                    dependencies=oversized,
                    operation=self.operation({"publish-deps": "limit"}),
                )
        self.assertEqual(caught.exception.code, LIMIT_EXCEEDED)


if __name__ == "__main__":  # pragma: no cover - manual run
    unittest.main()
