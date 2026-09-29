#!/usr/bin/env python3
"""A13: archive, recycle bin, and reference-safe permanent deletion.

The rules under test are the ones R13 names: archiving or trashing changes
discovery only and never breaks a reference; restoring keeps the ID and a
name clash must be resolved; permanent deletion is fail-closed, needs a
complete reference scan, and refuses while any in-registry reference exists;
deleting workbench data never touches the source folder, and a cross-project
copy survives.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from design_playbook_workbench.assets import AssetService, digest_bytes
from design_playbook_workbench.blobs import BlobStore
from design_playbook_workbench.canvas import CanvasService
from design_playbook_workbench.components import ComponentService
from design_playbook_workbench.errors import (
    CONFLICT,
    INVALID_INPUT,
    WorkbenchError,
)
from design_playbook_workbench.lifecycle import LifecycleService
from design_playbook_workbench.reuse import ReuseService
from design_playbook_workbench.service import Operation, WorkbenchService
from design_playbook_workbench.store import Store, WorkbenchDataDirectory


class LifecycleTestCase(unittest.TestCase):
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
            store=self.store, service=self.service, assets=self.assets,
            reuse=self.reuse, blobs=self.blobs,
        )
        self.canvases = CanvasService(
            store=self.store, service=self.service, components=self.components,
            reuse=self.reuse, blobs=self.blobs,
        )
        self.lifecycle = LifecycleService(
            store=self.store, service=self.service, assets=self.assets
        )
        self._operations = 0
        self.project_dir = self.base / "project"
        self.project_dir.mkdir()
        self.project_id = self._register(self.project_dir, "Design")

    def tearDown(self) -> None:
        self.store.close()
        self._tmp.cleanup()

    def operation(self, payload: dict, *, expected: int | None = None) -> Operation:
        self._operations += 1
        return Operation(
            operation_id=f"op_life_{self._operations:08d}",
            payload=payload,
            expected_counter=expected,
        )

    def _register(self, path: Path, name: str) -> str:
        candidate = self.service.probe_folder(path)
        target = self.service.register_project(
            path=candidate.canonical_path,
            candidate_id=candidate.candidate_id,
            name=name,
            operation=self.operation({"action": "register-project"}),
        )["result"]
        project_id = target["projectId"]
        counter = int(self.store.project(project_id)["counter"])
        self.service.set_grants(
            project_id,
            scopes=["read", "write"],
            operation=Operation(
                operation_id=f"op_grant_{name}",
                payload={"scopes": ["read", "write"]},
                expected_counter=counter,
            ),
        )
        return project_id

    def import_asset(self, name: str, body: bytes = b"# Brand\n", *, project_id=None) -> dict:
        project_id = project_id or self.project_id
        root = Path(self.service.require_project(project_id, scope="read")["canonicalPath"])
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
        asset = self.assets.import_selection(
            project_id,
            selections=[name],
            operation=self.operation({"action": "imports", "name": name}),
        )["result"]["asset"]
        return asset

    def publish(self, asset_id: str, *, project_id=None) -> dict:
        return self.assets.publish_revision(
            project_id or self.project_id,
            asset_id,
            operation=self.operation({"action": "publish"}),
        )["result"]


class ArchiveTrashRestoreTest(LifecycleTestCase):
    def test_archive_and_unarchive_keep_content_and_references(self) -> None:
        asset = self.import_asset("brand.md")
        self.publish(asset["assetId"])
        revision = self.store.latest_revision(asset["assetId"])
        archived = self.lifecycle.archive(
            self.project_id, asset["assetId"],
            operation=self.operation({"action": "archive"}),
        )["result"]
        self.assertEqual(archived["lifecycle"], "archived")
        # The published revision is still readable while archived.
        self.assertEqual(
            self.store.latest_revision(asset["assetId"])["revision_id"],
            revision["revision_id"],
        )
        browse = self.lifecycle.browse(self.project_id)
        self.assertEqual(browse["counts"]["archived"], 1)
        self.assertEqual(browse["counts"]["published"], 0)

        restored = self.lifecycle.unarchive(
            self.project_id, asset["assetId"],
            operation=self.operation({"action": "unarchive"}),
        )["result"]
        self.assertEqual(restored["lifecycle"], "published")

    def test_trash_and_restore_keep_the_same_id(self) -> None:
        asset = self.import_asset("brand.md")
        self.publish(asset["assetId"])
        self.lifecycle.trash(
            self.project_id, asset["assetId"],
            operation=self.operation({"action": "trash"}),
        )
        self.assertEqual(
            self.lifecycle.browse(self.project_id)["counts"]["trashed"], 1
        )
        restored = self.lifecycle.restore(
            self.project_id, asset["assetId"],
            operation=self.operation({"action": "restore"}),
        )["result"]
        self.assertEqual(restored["assetId"], asset["assetId"])
        self.assertEqual(restored["lifecycle"], "published")
        self.assertFalse(restored["renamed"])

    def test_restore_requires_resolving_a_name_conflict(self) -> None:
        first = self.import_asset("brand.md")
        self.publish(first["assetId"])
        self.lifecycle.trash(
            self.project_id, first["assetId"],
            operation=self.operation({"action": "trash"}),
        )
        # A new asset takes the same name while the first is in the bin.
        second = self.import_asset("brand.md")
        self.publish(second["assetId"])
        with self.assertRaises(WorkbenchError) as caught:
            self.lifecycle.restore(
                self.project_id, first["assetId"],
                operation=self.operation({"action": "restore"}),
            )
        self.assertEqual(caught.exception.code, CONFLICT)
        # A conflicting new name is refused too.
        with self.assertRaises(WorkbenchError) as caught:
            self.lifecycle.restore(
                self.project_id, first["assetId"], name=second["name"],
                operation=self.operation({"action": "restore"}),
            )
        self.assertEqual(caught.exception.code, CONFLICT)
        restored = self.lifecycle.restore(
            self.project_id, first["assetId"], name="brand-restored.md",
            operation=self.operation({"action": "restore"}),
        )["result"]
        self.assertTrue(restored["renamed"])
        self.assertEqual(restored["name"], "brand-restored.md")

    def test_transitions_respect_the_allowed_states(self) -> None:
        asset = self.import_asset("brand.md")
        self.publish(asset["assetId"])
        self.lifecycle.trash(
            self.project_id, asset["assetId"],
            operation=self.operation({"action": "trash"}),
        )
        # Cannot archive from the recycle bin, and cannot restore something
        # that is not trashed.
        with self.assertRaises(WorkbenchError) as caught:
            self.lifecycle.archive(
                self.project_id, asset["assetId"],
                operation=self.operation({"action": "archive"}),
            )
        self.assertEqual(caught.exception.code, CONFLICT)
        self.lifecycle.restore(
            self.project_id, asset["assetId"],
            operation=self.operation({"action": "restore"}),
        )
        with self.assertRaises(WorkbenchError) as caught:
            self.lifecycle.restore(
                self.project_id, asset["assetId"],
                operation=self.operation({"action": "restore"}),
            )
        self.assertEqual(caught.exception.code, CONFLICT)


class ReferenceReportTest(LifecycleTestCase):
    def test_the_report_names_every_kind_of_reference(self) -> None:
        token = self.import_asset("tokens/brand.json", b'{"color": {"brand": "#1f4fd8"}}')
        self.publish(token["assetId"])
        token_rev = self.store.latest_revision(token["assetId"])
        # A component that depends on the token set.
        component = self.import_asset("components/button.md", b"# Button\n")
        self.reuse.publish_with_dependencies(
            self.project_id,
            component["assetId"],
            dependencies=[
                {"assetId": token["assetId"], "revisionId": token_rev["revision_id"]}
            ],
            operation=self.operation({"action": "publish-deps"}),
        )
        # An instance and a derived asset.
        self.reuse.create_instance(
            self.project_id, token["assetId"],
            operation=self.operation({"action": "instances"}),
        )
        self.reuse.derive_or_copy(
            self.project_id, token["assetId"], mode="derive",
            operation=self.operation({"action": "derive"}),
        )
        report = self.lifecycle.reference_report(self.project_id, token["assetId"])
        self.assertTrue(report["indexComplete"])
        self.assertFalse(report["deletable"])
        self.assertEqual(len(report["instances"]), 1)
        self.assertEqual(
            [row["assetId"] for row in report["dependents"]], [component["assetId"]]
        )
        self.assertEqual(len(report["lineageChildren"]), 1)
        self.assertEqual(report["lineageChildren"][0]["relation"], "derived-from")
        self.assertTrue(any("跨项目" in b for b in report["boundaries"]))

    def test_a_canvas_reference_blocks_deletion(self) -> None:
        component = self.import_asset("components/button.md", b"# Button\n")
        self.publish(component["assetId"])
        instance = self.reuse.create_instance(
            self.project_id, component["assetId"],
            operation=self.operation({"action": "instances"}),
        )["result"]
        created = self.canvases.create(
            self.project_id, name="画布",
            document={
                "name": "画布",
                "boards": [
                    {"id": "b1", "name": "首页", "width": 1200, "height": 800,
                     "nodes": [
                         {"id": "inst", "type": "instance",
                          "props": {"instanceId": instance["instanceId"]},
                          "layout": {"x": 0, "y": 0, "width": 200, "height": 80, "z": 0}},
                     ], "flowEdges": []},
                ],
            },
            operation=self.operation({"action": "canvases"}),
        )["result"]
        self.assertTrue(created["canvas"]["canvasId"])
        report = self.lifecycle.reference_report(self.project_id, component["assetId"])
        self.assertEqual(len(report["canvasReferences"]), 1)
        self.assertFalse(report["deletable"])

    def test_a_corrupt_canvas_marks_the_index_incomplete(self) -> None:
        component = self.import_asset("components/button.md", b"# Button\n")
        self.publish(component["assetId"])
        created = self.canvases.create(
            self.project_id, name="画布",
            document={
                "name": "画布",
                "boards": [
                    {"id": "b1", "name": "首页", "width": 1200, "height": 800,
                     "nodes": [], "flowEdges": []},
                ],
            },
            operation=self.operation({"action": "canvases"}),
        )["result"]
        # Corrupt the stored canvas document directly.
        self.store.connection.execute(
            "UPDATE canvases SET document_json = ? WHERE canvas_id = ?",
            ("{not json", created["canvas"]["canvasId"]),
        )
        report = self.lifecycle.reference_report(self.project_id, component["assetId"])
        self.assertFalse(report["indexComplete"])
        self.assertFalse(report["deletable"])


class HardDeleteTest(LifecycleTestCase):
    def test_unreferenced_asset_deletes_and_source_hash_is_unchanged(self) -> None:
        asset = self.import_asset("brand.md")
        self.publish(asset["assetId"])
        source_hash = digest_bytes((self.project_dir / "brand.md").read_bytes())
        # A confirm flag is required.
        with self.assertRaises(WorkbenchError) as caught:
            self.lifecycle.hard_delete(
                self.project_id, asset["assetId"], confirm=False,
                operation=self.operation({"action": "hard-delete"}),
            )
        self.assertEqual(caught.exception.code, INVALID_INPUT)
        deleted = self.lifecycle.hard_delete(
            self.project_id, asset["assetId"], confirm=True,
            operation=self.operation({"action": "hard-delete"}),
        )["result"]
        self.assertEqual(deleted["assetId"], asset["assetId"])
        self.assertIsNone(self.store.asset(asset["assetId"]))
        # The local source file is untouched.
        self.assertEqual(
            digest_bytes((self.project_dir / "brand.md").read_bytes()), source_hash
        )
        self.assertTrue((self.project_dir / "brand.md").exists())

    def test_a_referenced_asset_is_refused_until_detached(self) -> None:
        component = self.import_asset("components/button.md", b"# Button\n")
        self.publish(component["assetId"])
        instance = self.reuse.create_instance(
            self.project_id, component["assetId"],
            operation=self.operation({"action": "instances"}),
        )["result"]
        with self.assertRaises(WorkbenchError) as caught:
            self.lifecycle.hard_delete(
                self.project_id, component["assetId"], confirm=True,
                operation=self.operation({"action": "hard-delete"}),
            )
        self.assertEqual(caught.exception.code, CONFLICT)
        self.assertIsNotNone(self.store.asset(component["assetId"]))
        # Detaching the instance clears the block.
        self.store.delete_instance(instance["instanceId"])
        deleted = self.lifecycle.hard_delete(
            self.project_id, component["assetId"], confirm=True,
            operation=self.operation({"action": "hard-delete"}),
        )["result"]
        self.assertEqual(deleted["assetId"], component["assetId"])

    def test_a_cross_project_copy_survives_deletion(self) -> None:
        other_dir = self.base / "other"
        other_dir.mkdir()
        other_id = self._register(other_dir, "Other")
        source = self.import_asset("brand.md")
        self.publish(source["assetId"])
        imported = self.reuse.import_closure(
            self.project_id,
            source_asset_id=source["assetId"],
            source_revision_id=None,
            mode="copy",
            target_project_id=other_id,
            operation=self.operation({"action": "import-closure"}),
        )["result"]
        local_asset_id = imported["assetId"]
        report = self.lifecycle.reference_report(self.project_id, source["assetId"])
        self.assertEqual(len(report["crossProjectCopies"]), 1)
        # A cross-project copy does not block deleting the source, and the
        # copy is untouched after the source is gone.
        deleted = self.lifecycle.hard_delete(
            self.project_id, source["assetId"], confirm=True,
            operation=self.operation({"action": "hard-delete"}),
        )["result"]
        self.assertEqual(len(deleted["crossProjectCopies"]), 1)
        self.assertIsNone(self.store.asset(source["assetId"]))
        self.assertIsNotNone(self.store.asset(local_asset_id))


class ProjectLifecycleTest(LifecycleTestCase):
    def test_project_archive_and_deletion_impact(self) -> None:
        asset = self.import_asset("brand.md")
        self.publish(asset["assetId"])
        archived = self.lifecycle.archive_project(
            self.project_id, archived=True,
            operation=self.operation({"action": "project-archive"}),
        )["result"]
        self.assertTrue(archived["archived"])
        self.assertTrue(self.lifecycle.browse(self.project_id)["projectArchived"])
        self.lifecycle.archive_project(
            self.project_id, archived=False,
            operation=self.operation({"action": "project-unarchive"}),
        )
        impact = self.lifecycle.project_deletion_impact(self.project_id)
        self.assertEqual(impact["assetCount"], 1)
        self.assertTrue(any("源仓库" in b for b in impact["boundaries"]))

    def test_removing_a_project_never_deletes_the_source_folder(self) -> None:
        asset = self.import_asset("brand.md")
        self.publish(asset["assetId"])
        source_hash = digest_bytes((self.project_dir / "brand.md").read_bytes())
        counter = int(self.store.project(self.project_id)["counter"])
        self.service.remove_project(
            self.project_id,
            operation=self.operation({"action": "remove"}, expected=counter),
        )
        self.assertFalse(self.store.project_exists(self.project_id))
        # The maintainer's source is intact.
        self.assertTrue((self.project_dir / "brand.md").exists())
        self.assertEqual(
            digest_bytes((self.project_dir / "brand.md").read_bytes()), source_hash
        )


if __name__ == "__main__":  # pragma: no cover - manual run
    unittest.main()
