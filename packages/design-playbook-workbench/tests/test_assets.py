#!/usr/bin/env python3
"""A03 (domain half): read-only import, capability honesty, discovery.

Every fixture here is a real temporary directory: the import walks the
real filesystem, stores real bytes, and the negatives are the ones that
matter -- oversized batches that must leave no half-imported asset,
credential files that must never become reusable assets, archives that
are refused instead of unpacked, and capability labels that are never
inferred from a file extension.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from design_playbook_workbench.assets import (
    CAPABILITY_NATIVE_EDITABLE,
    CAPABILITY_REFERENCE,
    CAPABILITY_RUNNABLE_VERIFIED,
    CAPABILITY_SOURCE_UNVERIFIED,
    CAPABILITY_STATIC_PREVIEW,
    AssetService,
)
from design_playbook_workbench.blobs import BlobStore, digest_bytes
from design_playbook_workbench.errors import (
    CONFLICT,
    CORRUPT_CONTENT,
    INVALID_TARGET,
    LIMIT_EXCEEDED,
    MISSING_DEPENDENCY,
    UNSUPPORTED,
    UNAUTHORIZED,
    WorkbenchError,
)
from design_playbook_workbench.service import Operation, WorkbenchService
from design_playbook_workbench.store import Store, WorkbenchDataDirectory

from tests.harness import make_directory_link


class AssetTestCase(unittest.TestCase):
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
        self.project = self.base / "project"
        self.project.mkdir()
        self._operations = 0
        candidate = self.service.probe_folder(self.project)
        self.target = self.service.register_project(
            path=candidate.canonical_path,
            candidate_id=candidate.candidate_id,
            name="Assets",
            operation=self.operation({"action": "register-project"}),
        )["result"]
        self.project_id = self.target["projectId"]

    def tearDown(self) -> None:
        self.store.close()
        self._tmp.cleanup()

    def operation(self, payload: dict, *, expected: int | None = None, operation_id: str | None = None):
        if operation_id is None:
            self._operations += 1
            operation_id = f"op_asset_{self._operations:08d}"
        return Operation(
            operation_id=operation_id, payload=payload, expected_counter=expected
        )

    def write(self, relative: str, text: str = "", data: bytes | None = None) -> Path:
        path = self.project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data if data is not None else text.encode("utf-8"))
        return path

    def grant(self, scopes: list[str]) -> None:
        counter = int(self.store.project(self.project_id)["counter"])
        self.service.set_grants(
            self.project_id,
            scopes=scopes,
            operation=self.operation({"scopes": scopes}, expected=counter),
        )

    def import_assets(self, selections: list, *, operation: Operation | None = None) -> dict:
        return self.assets.import_selection(
            self.project_id,
            selections=selections,
            operation=operation or self.operation({"selections": selections}),
        )["result"]

    def publish(self, asset_id: str) -> dict:
        self.grant(["read", "write"])
        return self.assets.publish_revision(
            self.project_id, asset_id, operation=self.operation({"publish": asset_id})
        )["result"]


class ImportClassificationTest(AssetTestCase):
    def test_markdown_design_and_notes_import_as_references(self) -> None:
        self.write("DESIGN.md", "# Design\n\nBaseline.\n")
        self.write("notes/decisions.md", "# Decisions\n")
        result = self.import_assets(["DESIGN.md", "notes/decisions.md"])
        self.assertEqual(result["fileCount"], 2)
        asset = result["asset"]
        self.assertEqual(asset["capabilities"], [CAPABILITY_REFERENCE])
        self.assertEqual(asset["lifecycle"], "draft")
        self.assertIsNone(asset["revisionNumber"])
        for entry in asset["manifest"]:
            self.assertTrue(self.blobs.verify(entry["contentHash"]))
        self.assertEqual(result["sourceLocators"][0]["path"], "DESIGN.md")
        self.assertEqual(result["sourceLocators"][0]["sourceHash"],
                         digest_bytes(b"# Design\n\nBaseline.\n"))

    def test_static_package_imports_as_one_previewable_asset(self) -> None:
        self.write("site/index.html", "<!doctype html><h1>Hi</h1>\n")
        self.write("site/app.css", "h1 { color: red; }\n")
        self.write("site/app.js", "console.log('hi');\n")
        result = self.import_assets(["site"])
        asset = result["asset"]
        self.assertEqual(asset["kind"], "static-package")
        self.assertEqual(
            sorted(asset["capabilities"]),
            [CAPABILITY_REFERENCE, CAPABILITY_STATIC_PREVIEW],
        )
        self.assertEqual(
            sorted(entry["path"] for entry in asset["manifest"]),
            ["site/app.css", "site/app.js", "site/index.html"],
        )

    def test_typescript_source_is_unverified_never_runnable_or_editable(self) -> None:
        self.write("components/Button.tsx", "export const Button = () => null;\n")
        result = self.import_assets(["components"])
        capabilities = result["asset"]["capabilities"]
        self.assertIn(CAPABILITY_SOURCE_UNVERIFIED, capabilities)
        self.assertNotIn(CAPABILITY_RUNNABLE_VERIFIED, capabilities)
        self.assertNotIn(CAPABILITY_NATIVE_EDITABLE, capabilities)

    def test_images_tokens_and_run_artifacts_are_classified_honestly(self) -> None:
        png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
        self.write("shots/home.png", data=png)
        self.write("tokens/colors.json", '{"color": {"brand": "#123456"}}\n')
        self.write("run/run-2026.json", '{"stage": "preview"}\n')
        by_root = {}
        for selection in ("shots/home.png", "tokens/colors.json", "run/run-2026.json"):
            by_root[selection] = self.import_assets([selection])["asset"]
        self.assertEqual(by_root["shots/home.png"]["kind"], "image")
        self.assertEqual(by_root["shots/home.png"]["capabilities"], [CAPABILITY_REFERENCE])
        self.assertEqual(by_root["tokens/colors.json"]["kind"], "tokens")
        self.assertEqual(by_root["run/run-2026.json"]["kind"], "run-artifact")

    def test_invalid_utf8_text_stays_a_reference_only_binary(self) -> None:
        self.write("broken.md", data=b"\xff\xfe\x00 not utf-8")
        asset = self.import_assets(["broken.md"])["asset"]
        self.assertEqual(asset["kind"], "binary")
        self.assertEqual(asset["capabilities"], [CAPABILITY_REFERENCE])
        self.assertIn("binary", [entry["encoding"] for entry in asset["manifest"]])

    def test_archives_are_refused_rather_than_unpacked(self) -> None:
        self.write("bundle.zip", data=b"PK\x03\x04 fake archive")
        with self.assertRaises(WorkbenchError) as caught:
            self.import_assets(["bundle.zip"])
        self.assertEqual(caught.exception.code, UNSUPPORTED)
        self.assertEqual(len(self.store.project_assets(self.project_id)), 0)


class ImportBoundaryTest(AssetTestCase):
    def test_the_documented_limits_are_exactly_the_spec_numbers(self) -> None:
        from design_playbook_workbench import assets as module

        self.assertEqual(module.MAX_FILE_BYTES, 20 * 1024 * 1024)
        self.assertEqual(module.MAX_BATCH_BYTES, 200 * 1024 * 1024)
        self.assertEqual(module.MAX_BATCH_FILES, 1000)

    def test_an_oversized_file_rejects_the_whole_batch(self) -> None:
        from design_playbook_workbench import assets as module

        self.write("notes.md", "# fine\n")
        self.write("too-big.md", "x" * 200)
        # The enforcement path is exercised with a small limit: the real
        # 20 MiB constant is asserted above, and allocating hundreds of MiB
        # in a test suite is not worth it.
        with mock.patch.object(module, "MAX_FILE_BYTES", 64):
            with self.assertRaises(WorkbenchError) as caught:
                self.import_assets(["notes.md", "too-big.md"])
        self.assertEqual(caught.exception.code, LIMIT_EXCEEDED)
        # No half-imported record survives a rejected batch.
        self.assertEqual(self.store.project_assets(self.project_id), [])

    def test_an_oversized_batch_rejects_the_whole_import(self) -> None:
        from design_playbook_workbench import assets as module

        for index in range(3):
            self.write(f"part-{index}.md", "y" * 120)
        with mock.patch.object(module, "MAX_BATCH_BYTES", 200):
            with self.assertRaises(WorkbenchError) as caught:
                self.import_assets([f"part-{index}.md" for index in range(3)])
        self.assertEqual(caught.exception.code, LIMIT_EXCEEDED)
        self.assertEqual(self.store.project_assets(self.project_id), [])

    def test_too_many_files_rejects_the_whole_import(self) -> None:
        many = self.project / "many"
        many.mkdir()
        for index in range(1001):
            (many / f"file-{index}.txt").write_text("x", encoding="utf-8")
        with self.assertRaises(WorkbenchError) as caught:
            self.import_assets(["many"])
        self.assertEqual(caught.exception.code, LIMIT_EXCEEDED)
        self.assertEqual(self.store.project_assets(self.project_id), [])

    def test_credentials_are_skipped_inside_a_folder_and_refused_explicitly(self) -> None:
        self.write("site/index.html", "<h1>Hi</h1>\n")
        self.write("site/.env", "API_KEY=super-secret-value\n")
        self.write("site/server.pem", "-----BEGIN PRIVATE KEY-----\n")
        self.write("site/id_rsa", "ssh-rsa AAAA\n")
        result = self.import_assets(["site"])
        paths = [entry["path"] for entry in result["asset"]["manifest"]]
        self.assertEqual(paths, ["site/index.html"])
        self.assertTrue(any("凭证" in warning for warning in result["warnings"]))
        # The secret bytes never reached blob storage.
        for content_hash in self.blobs.iter_hashes():
            self.assertNotIn(b"super-secret-value", self.blobs.read(content_hash))
        with self.assertRaises(WorkbenchError) as caught:
            self.import_assets(["site/.env"])
        self.assertEqual(caught.exception.code, INVALID_TARGET)

    def test_dependency_and_vcs_folders_are_excluded_from_enumeration(self) -> None:
        self.write("site/index.html", "<h1>Hi</h1>\n")
        self.write("site/node_modules/pkg/index.js", "module.exports = 1;\n")
        self.write("site/.git/config", "[core]\n")
        result = self.import_assets(["site"])
        paths = [entry["path"] for entry in result["asset"]["manifest"]]
        self.assertEqual(paths, ["site/index.html"])

    def test_paths_outside_the_project_are_refused(self) -> None:
        outside = self.base / "outside.md"
        outside.write_text("# outside\n", encoding="utf-8")
        for selection in (
            "../outside.md",
            str(outside),
            "/absolute.md",
            "missing.md",
            "..",
        ):
            with self.subTest(selection=selection):
                with self.assertRaises(WorkbenchError) as caught:
                    self.import_assets([selection])
                self.assertIn(
                    caught.exception.code, (INVALID_TARGET,)
                )
        self.assertEqual(self.store.project_assets(self.project_id), [])

    def test_a_junction_inside_the_project_cannot_be_imported_through(self) -> None:
        outside = self.base / "elsewhere"
        outside.mkdir()
        (outside / "secret.md").write_text("# private\n", encoding="utf-8")
        link = self.project / "linked"
        if not make_directory_link(link, outside):
            self.skipTest("directory links are unavailable on this host")
        with self.assertRaises(WorkbenchError) as caught:
            self.import_assets(["linked/secret.md"])
        self.assertEqual(caught.exception.code, INVALID_TARGET)

    def test_import_reads_only_inside_the_project_and_never_outside(self) -> None:
        outside = self.base / "outside.md"
        outside.write_text("# outside\n", encoding="utf-8")
        self.write("notes.md", "# notes\n")
        imported = self.import_assets(["notes.md"])["asset"]
        manifest = imported["manifest"][0]
        # The locator names the project-relative path, and the blob holds the
        # project's bytes, not the identically named file outside.
        self.assertEqual(manifest["path"], "notes.md")
        self.assertEqual(self.blobs.read(manifest["contentHash"]), b"# notes\n")

    def test_the_batch_is_idempotent_for_one_operation_id(self) -> None:
        self.write("notes.md", "# notes\n")
        operation = self.operation({"selections": ["notes.md"]}, operation_id="op_import_once_1")
        first = self.assets.import_selection(
            self.project_id, selections=["notes.md"], operation=operation
        )
        second = self.assets.import_selection(
            self.project_id, selections=["notes.md"], operation=operation
        )
        self.assertFalse(first["replayed"])
        self.assertTrue(second["replayed"])
        self.assertEqual(first["result"], second["result"])
        self.assertEqual(len(self.store.project_assets(self.project_id)), 1)


class BlobContractTest(AssetTestCase):
    def test_content_is_stored_before_the_directory_transaction(self) -> None:
        self.write("notes.md", "# notes\n")
        with mock.patch.object(
            self.store, "create_asset", side_effect=RuntimeError("injected")
        ):
            with self.assertRaises(RuntimeError):
                self.import_assets(["notes.md"])
        self.assertEqual(self.store.project_assets(self.project_id), [])
        self.assertEqual(self.store.import_record.__self__.all_import_files(), [])
        # The bytes are on disk, and are reported as unreferenced rather
        # than silently deleted.
        expected = digest_bytes(b"# notes\n")
        self.assertTrue(self.blobs.verify(expected))
        self.assertEqual(self.blobs.unreferenced(set()), [expected])

    def test_blob_integrity_is_checked_on_read(self) -> None:
        record = self.blobs.put(b"hello")
        self.assertEqual(self.blobs.read(record.content_hash), b"hello")
        self.assertTrue(self.blobs.exists(record.content_hash))
        path = self.blobs.path_for(record.content_hash)
        path.write_bytes(b"tampered")
        with self.assertRaises(WorkbenchError) as caught:
            self.blobs.read(record.content_hash)
        self.assertEqual(caught.exception.code, CORRUPT_CONTENT)
        self.assertFalse(self.blobs.verify(record.content_hash))

    def test_unknown_and_malformed_hashes_are_refused(self) -> None:
        for bad in ("sha256:" + "0" * 64, "not-a-hash", "", "sha256:xyz"):
            with self.subTest(bad=bad):
                with self.assertRaises(WorkbenchError):
                    self.blobs.read(bad)


class PublishTest(AssetTestCase):
    def test_publishing_freezes_an_immutable_revision(self) -> None:
        self.write("site/index.html", "<h1>Hi</h1>\n")
        asset = self.import_assets(["site"])["asset"]
        published = self.publish(asset["assetId"])
        self.assertEqual(published["revisionNumber"], 1)
        self.assertEqual(published["lifecycle"], "published")
        revision = self.store.latest_revision(asset["assetId"])
        self.assertEqual(revision["revision_number"], 1)
        manifest = json.loads(revision["manifest_json"])
        self.assertTrue(self.blobs.verify(manifest[0]["contentHash"]))
        # Editing the source file afterwards does not change the revision.
        self.write("site/index.html", "<h1>Changed on disk</h1>\n")
        detail = self.assets.asset_detail(self.project_id, asset["assetId"])["asset"]
        self.assertEqual(detail["revisionNumber"], 1)
        self.assertEqual(
            json.loads(revision["manifest_json"])[0]["contentHash"],
            detail["manifest"][0]["contentHash"],
        )
        self.assertNotEqual(
            self.blobs.read(manifest[0]["contentHash"]), b"<h1>Changed on disk</h1>\n"
        )

    def test_publishing_requires_write_scope_and_valid_content(self) -> None:
        self.write("notes.md", "# notes\n")
        asset = self.import_assets(["notes.md"])["asset"]
        with self.assertRaises(WorkbenchError) as caught:
            self.assets.publish_revision(
                self.project_id, asset["assetId"], operation=self.operation({"publish": 1})
            )
        self.assertEqual(caught.exception.code, UNAUTHORIZED)
        self.grant(["read", "write"])
        blob = asset["manifest"][0]["contentHash"]
        self.blobs.path_for(blob).unlink()
        with self.assertRaises(WorkbenchError) as caught:
            self.assets.publish_revision(
                self.project_id, asset["assetId"], operation=self.operation({"publish": 2})
            )
        self.assertEqual(caught.exception.code, CORRUPT_CONTENT)

    def test_a_verified_capability_cannot_be_declared_at_publish_time(self) -> None:
        self.write("site/index.html", "<h1>Hi</h1>\n")
        asset = self.import_assets(["site"])["asset"]
        draft = self.store.draft(asset["assetId"])
        attributes = json.loads(draft["attributes_json"])
        attributes["capabilities"] = [CAPABILITY_REFERENCE, CAPABILITY_RUNNABLE_VERIFIED]
        self.store.update_draft(
            asset_id=asset["assetId"],
            tags=[],
            attributes=attributes,
            now="2026-09-26T12:00:00Z",
        )
        self.grant(["read", "write"])
        with self.assertRaises(WorkbenchError) as caught:
            self.assets.publish_revision(
                self.project_id, asset["assetId"], operation=self.operation({"publish": 3})
            )
        self.assertEqual(caught.exception.code, MISSING_DEPENDENCY)
        self.assertEqual(self.store.asset_revisions(asset["assetId"]), [])


class DiscoveryTest(AssetTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.write("brand/brand.md", "# Brand\n")
        self.write("brand/brand-tokens.json", '{"color": {}}\n')
        self.write("pages/home/index.html", "<h1>Home</h1>\n")
        self.write("widgets/chart.tsx", "export const Chart = () => null;\n")
        self.alpha = self.import_assets(["brand/brand.md"])["asset"]
        self.tokens = self.import_assets(["brand/brand-tokens.json"])["asset"]
        self.page = self.import_assets(["pages/home"])["asset"]
        self.widget = self.import_assets(["widgets/chart.tsx"])["asset"]

    def test_filters_and_matching_reasons(self) -> None:
        listing = self.assets.list_assets(self.project_id, query="brand")
        items = listing["assets"]
        # Name matches rank above the tag match; within one rank the order
        # is the documented (updated, stable id) tie-break, not alphabet.
        self.assertEqual(
            {item["name"] for item in items[:2]}, {"brand.md", "brand-tokens.json"}
        )
        self.assertTrue(all(item["matchedOn"] == "name" for item in items[:2]))
        self.assertEqual(len(items), 2)

        by_kind = self.assets.list_assets(self.project_id, kind="static-package")
        self.assertEqual([item["name"] for item in by_kind["assets"]], ["home"])
        by_capability = self.assets.list_assets(
            self.project_id, capability=CAPABILITY_SOURCE_UNVERIFIED
        )
        self.assertEqual([item["name"] for item in by_capability["assets"]], ["chart.tsx"])
        by_lifecycle = self.assets.list_assets(self.project_id, lifecycle="published")
        self.assertEqual(by_lifecycle["assets"], [])

    def test_tag_matches_rank_below_name_matches(self) -> None:
        self.store.update_draft(
            asset_id=self.widget["assetId"],
            tags=["brand"],
            attributes=json.loads(
                self.store.draft(self.widget["assetId"])["attributes_json"]
            ),
            now="2026-09-26T12:00:00Z",
        )
        listing = self.assets.list_assets(self.project_id, query="brand")
        reasons = {item["name"]: item["matchedOn"] for item in listing["assets"]}
        self.assertEqual(reasons["brand.md"], "name")
        self.assertEqual(reasons["chart.tsx"], "tag")
        self.assertEqual(listing["assets"][-1]["name"], "chart.tsx")
    def test_ordering_is_deterministic_and_detail_is_complete(self) -> None:
        first = [item["assetId"] for item in self.assets.list_assets(self.project_id)["assets"]]
        second = [item["assetId"] for item in self.assets.list_assets(self.project_id)["assets"]]
        self.assertEqual(first, second)
        detail = self.assets.asset_detail(self.project_id, self.page["assetId"])["asset"]
        self.assertEqual(detail["kind"], "static-package")
        self.assertEqual(detail["roots"], ["pages/home"])
        self.assertEqual(detail["revisions"], [])
        self.assertEqual(
            {locator["path"] for locator in detail["sourceLocators"]},
            {"pages/home/index.html"},
        )

    def test_assets_survive_a_restart(self) -> None:
        self.store.close()
        reopened = Store(self.data_dir.database_path)
        try:
            service = WorkbenchService(store=reopened, data_dir=self.data_dir)
            assets = AssetService(
                store=reopened, service=service, blobs=self.blobs
            )
            listing = assets.list_assets(self.project_id)["assets"]
            self.assertEqual(len(listing), 4)
            detail = assets.asset_detail(self.project_id, self.alpha["assetId"])["asset"]
            self.assertEqual(detail["name"], "brand.md")
        finally:
            reopened.close()
            self.store = Store(self.data_dir.database_path)


class MutationReplayBindingTest(AssetTestCase):
    """The one replay gate binds the target, not just digest and kind.

    Reusing an operation id against a different or nonexistent asset must
    conflict; it must never return the originally recorded asset's success.
    """

    def test_replaying_an_operation_never_returns_another_assets_success(self) -> None:
        self.write("brand.md", "# Brand\n")
        asset_id = self.import_assets(["brand.md"])["asset"]["assetId"]
        self.grant(["read", "write"])
        operation = self.operation({"action": "publish", "assetId": asset_id})

        first = self.assets.publish_revision(self.project_id, asset_id, operation=operation)
        self.assertFalse(first["replayed"])
        self.assertIsNone(self.store.asset("nonexistent-asset"))

        # Same operation id, different (nonexistent) target: a conflict.
        with self.assertRaises(WorkbenchError) as caught:
            self.assets.publish_revision(
                self.project_id, "nonexistent-asset", operation=operation
            )
        self.assertEqual(caught.exception.code, CONFLICT)

        # The exact same operation on the same target is idempotent.
        again = self.assets.publish_revision(self.project_id, asset_id, operation=operation)
        self.assertTrue(again["replayed"])
        self.assertEqual(again["result"], first["result"])


if __name__ == "__main__":  # pragma: no cover - manual run
    unittest.main()
