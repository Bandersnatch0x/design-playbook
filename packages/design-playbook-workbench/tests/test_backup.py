#!/usr/bin/env python3
"""A14: consistency backup, verified restore to a new directory, migration.

The rules under test are the ones R14 names: a backup is a sealed archive
built from a consistency snapshot plus a fixed blob manifest, with no
credentials or source repo; a failed write leaves no finished archive;
restore is fail-closed (zip-slip, symlink entries, oversize, file-count, and
a newer schema are all rejected, every hash is verified) and goes to a new
directory without touching the original or replaying journals; a newer
schema database is refused on open while an older one migrates.
"""
from __future__ import annotations

import json
import os
from unittest.mock import patch
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path

from design_playbook_workbench.assets import AssetService
from design_playbook_workbench.backup import (
    BACKUP_FORMAT,
    BLOB_PREFIX,
    DATABASE_ENTRY,
    MANIFEST_NAME,
    BackupService,
)
from design_playbook_workbench.blobs import BlobStore, digest_bytes
from design_playbook_workbench.errors import (
    CONFLICT,
    CORRUPT_CONTENT,
    INVALID_INPUT,
    INVALID_TARGET,
    UNSUPPORTED,
    WorkbenchError,
)
from design_playbook_workbench.service import Operation, WorkbenchService
from design_playbook_workbench.store import SCHEMA_VERSION, Store, WorkbenchDataDirectory


class BackupTestCase(unittest.TestCase):
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
        self.backup = BackupService(
            store=self.store, service=self.service, data_dir=self.data_dir,
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
                operation_id="op_grant_backup",
                payload={"scopes": ["read", "write"]},
                expected_counter=counter,
            ),
        )
        # A published asset so the backup has real content.
        (self.project_dir / "brand.md").write_bytes(b"# Brand\n")
        asset = self.assets.import_selection(
            self.project_id, selections=["brand.md"],
            operation=self.operation({"action": "imports"}),
        )["result"]["asset"]
        self.assets.publish_revision(
            self.project_id, asset["assetId"],
            operation=self.operation({"action": "publish"}),
        )
        self.asset_id = asset["assetId"]

    def tearDown(self) -> None:
        self.store.close()
        self._tmp.cleanup()

    def operation(self, payload: dict) -> Operation:
        self._operations += 1
        return Operation(
            operation_id=f"op_backup_{self._operations:08d}", payload=payload
        )

    def make_backup(self) -> dict:
        return self.backup.create(
            destination=str(self.base / "backup.dpwb.zip"),
            operation=self.operation({"action": "create"}),
        )["result"]


class BackupCreateTest(BackupTestCase):
    def test_backup_is_sealed_with_no_credentials_or_source(self) -> None:
        result = self.make_backup()
        path = Path(result["path"])
        self.assertTrue(path.is_file())
        self.assertFalse(result["containsCredentials"])
        self.assertFalse(result["containsSourceRepo"])
        self.assertGreaterEqual(result["blobCount"], 1)
        with zipfile.ZipFile(path, "r") as archive:
            names = set(archive.namelist())
            self.assertIn(MANIFEST_NAME, names)
            self.assertIn(DATABASE_ENTRY, names)
            manifest = json.loads(archive.read(MANIFEST_NAME).decode("utf-8"))
            self.assertEqual(manifest["format"], BACKUP_FORMAT)
            self.assertEqual(manifest["schemaVersion"], SCHEMA_VERSION)
            # No session record / token / source file is packaged.
            self.assertFalse(any("session" in name for name in names))
            self.assertFalse(any(name.endswith("brand.md") for name in names))
            # The database hash matches the packaged bytes.
            self.assertEqual(
                digest_bytes(archive.read(DATABASE_ENTRY)), manifest["database"]["hash"]
            )

    def test_a_backup_cannot_be_written_inside_a_project_folder(self) -> None:
        with self.assertRaises(WorkbenchError) as caught:
            self.backup.create(
                destination=str(self.project_dir / "backup.zip"),
                operation=self.operation({"action": "create"}),
            )
        self.assertEqual(caught.exception.code, INVALID_TARGET)

    def test_verify_accepts_a_good_backup(self) -> None:
        result = self.make_backup()
        report = self.backup.verify(result["path"])
        self.assertTrue(report["valid"])
        self.assertEqual(report["schemaVersion"], SCHEMA_VERSION)
        self.assertEqual(report["blobCount"], result["blobCount"])


class BackupDestinationTest(BackupTestCase):
    """A backup is written where it is asked, never over live data, and an
    existing path is replaced only on a deliberate overwrite."""

    def test_a_backup_never_overwrites_workbench_storage(self) -> None:
        content_hash = next(iter(self.blobs.iter_hashes()))
        blob_path = self.blobs.path_for(content_hash)
        before = blob_path.read_bytes()
        with self.assertRaises(WorkbenchError) as caught:
            self.backup.create(
                destination=str(blob_path),
                operation=self.operation({"action": "create"}),
            )
        self.assertEqual(caught.exception.code, INVALID_TARGET)
        # The live blob is untouched.
        self.assertEqual(blob_path.read_bytes(), before)
        self.assertTrue(self.blobs.verify(content_hash))

    def test_an_existing_destination_is_refused_without_overwrite(self) -> None:
        existing = self.base / "already-there.zip"
        existing.write_bytes(b"keep me")
        with self.assertRaises(WorkbenchError) as caught:
            self.backup.create(
                destination=str(existing),
                operation=self.operation({"action": "create"}),
            )
        self.assertEqual(caught.exception.code, CONFLICT)
        self.assertEqual(existing.read_bytes(), b"keep me")
        # A deliberate overwrite replaces it with a real archive.
        result = self.backup.create(
            destination=str(existing),
            overwrite=True,
            operation=self.operation({"action": "create"}),
        )["result"]
        self.assertEqual(Path(result["path"]), existing)
        self.assertTrue(self.backup.verify(str(existing))["valid"])

    def test_partial_file_cannot_replace_a_live_blob(self) -> None:
        content_hash = next(iter(self.blobs.iter_hashes()))
        blob = self.blobs.path_for(content_hash)
        original = blob.read_bytes()
        target = self.base / "backup.zip"
        partial = target.with_suffix(".zip.partial")
        os.link(blob, partial)
        with self.assertRaises(WorkbenchError) as caught:
            self.backup.create(destination=str(target), operation=self.operation({"action": "create"}))
        self.assertEqual(caught.exception.code, CONFLICT)
        self.assertEqual(blob.read_bytes(), original)
        self.assertFalse(target.exists())

    def test_destination_created_during_backup_is_not_overwritten(self) -> None:
        target = self.base / "raced.zip"
        original_write = self.backup._write_archive
        def write_and_race(*args):
            original_write(*args)
            target.write_bytes(b"concurrent file")
        with patch.object(self.backup, "_write_archive", side_effect=write_and_race):
            with self.assertRaises(WorkbenchError) as caught:
                self.backup.create(destination=str(target), operation=self.operation({"action": "create"}))
        self.assertEqual(caught.exception.code, CONFLICT)
        self.assertEqual(target.read_bytes(), b"concurrent file")
        self.assertFalse(target.with_suffix(".zip.partial").exists())

    def test_the_default_backups_directory_stays_usable(self) -> None:
        result = self.backup.create(
            operation=self.operation({"action": "create"})
        )["result"]
        path = Path(result["path"])
        self.assertTrue(path.is_file())
        self.assertEqual(path.parent, self.data_dir.root / "backups")


class VerifyRejectionTest(BackupTestCase):
    def _tamper(self, mutate) -> Path:
        result = self.make_backup()
        source = Path(result["path"])
        tampered = self.base / "tampered.dpwb.zip"
        with zipfile.ZipFile(source, "r") as src:
            infos = src.infolist()
            data = {info.filename: src.read(info.filename) for info in infos}
        mutate(data)
        with zipfile.ZipFile(tampered, "w", zipfile.ZIP_DEFLATED) as dst:
            for name, body in data.items():
                dst.writestr(name, body)
        return tampered

    def test_a_corrupt_blob_is_rejected(self) -> None:
        def mutate(data: dict) -> None:
            blob_name = next(n for n in data if n.startswith(BLOB_PREFIX))
            data[blob_name] = b"corrupted"
        with self.assertRaises(WorkbenchError) as caught:
            self.backup.verify(str(self._tamper(mutate)))
        self.assertEqual(caught.exception.code, CORRUPT_CONTENT)

    def test_a_corrupt_database_is_rejected(self) -> None:
        def mutate(data: dict) -> None:
            data[DATABASE_ENTRY] = b"not a database"
        with self.assertRaises(WorkbenchError) as caught:
            self.backup.verify(str(self._tamper(mutate)))
        self.assertEqual(caught.exception.code, CORRUPT_CONTENT)

    def test_a_newer_schema_is_refused(self) -> None:
        def mutate(data: dict) -> None:
            manifest = json.loads(data[MANIFEST_NAME].decode("utf-8"))
            manifest["schemaVersion"] = SCHEMA_VERSION + 5
            data[MANIFEST_NAME] = json.dumps(manifest).encode("utf-8")
        with self.assertRaises(WorkbenchError) as caught:
            self.backup.verify(str(self._tamper(mutate)))
        self.assertEqual(caught.exception.code, UNSUPPORTED)

    def test_zip_slip_and_symlink_entries_are_refused(self) -> None:
        slip = self.base / "slip.zip"
        with zipfile.ZipFile(slip, "w") as archive:
            archive.writestr(MANIFEST_NAME, json.dumps({"format": BACKUP_FORMAT}))
            archive.writestr("../escape.txt", b"x")
        with self.assertRaises(WorkbenchError) as caught:
            self.backup.verify(str(slip))
        self.assertEqual(caught.exception.code, INVALID_INPUT)

        symlink = self.base / "symlink.zip"
        with zipfile.ZipFile(symlink, "w") as archive:
            info = zipfile.ZipInfo("blobs/link")
            info.external_attr = 0o120777 << 16  # symlink mode
            archive.writestr(info, "/etc/passwd")
            archive.writestr(MANIFEST_NAME, json.dumps({"format": BACKUP_FORMAT}))
        with self.assertRaises(WorkbenchError) as caught:
            self.backup.verify(str(symlink))
        self.assertEqual(caught.exception.code, INVALID_INPUT)

    def test_a_non_archive_is_refused(self) -> None:
        plain = self.base / "plain.txt"
        plain.write_bytes(b"hello")
        with self.assertRaises(WorkbenchError) as caught:
            self.backup.verify(str(plain))
        self.assertEqual(caught.exception.code, INVALID_INPUT)
        with self.assertRaises(WorkbenchError) as caught:
            self.backup.verify(str(self.base / "missing.zip"))
        self.assertEqual(caught.exception.code, INVALID_TARGET)


class RestoreTest(BackupTestCase):
    def test_restore_to_a_new_directory_preserves_the_original(self) -> None:
        result = self.make_backup()
        restore_dir = self.base / "restored"
        restored = self.backup.restore(
            archive_path=result["path"],
            target=str(restore_dir),
            operation=self.operation({"action": "restore"}),
        )["result"]
        self.assertEqual(restored["restoredDataDir"], str(restore_dir))
        self.assertFalse(restored["switched"])
        self.assertTrue(restored["reauthorizationRequired"])
        self.assertTrue(restored["integrity"]["referencedBlobsPresent"])
        # The original data directory is untouched and still active.
        self.assertTrue(self.data_dir.database_path.is_file())
        # The restored directory holds a working database with the asset.
        reopened = Store((restore_dir / "workbench.db"))
        try:
            self.assertIsNotNone(reopened.asset(self.asset_id))
            restored_blobs = BlobStore(restore_dir / "blobs")
            revision = reopened.latest_revision(self.asset_id)
            manifest = json.loads(revision["manifest_json"])
            self.assertTrue(restored_blobs.verify(manifest[0]["contentHash"]))
        finally:
            reopened.close()

    def test_restore_refuses_the_active_or_non_empty_directory(self) -> None:
        result = self.make_backup()
        with self.assertRaises(WorkbenchError) as caught:
            self.backup.restore(
                archive_path=result["path"], target=str(self.data_dir.root),
                operation=self.operation({"action": "restore"}),
            )
        self.assertEqual(caught.exception.code, CONFLICT)
        non_empty = self.base / "occupied"
        non_empty.mkdir()
        (non_empty / "keep.txt").write_bytes(b"x")
        with self.assertRaises(WorkbenchError) as caught:
            self.backup.restore(
                archive_path=result["path"], target=str(non_empty),
                operation=self.operation({"action": "restore"}),
            )
        self.assertEqual(caught.exception.code, CONFLICT)

    def test_restore_requires_an_absolute_target(self) -> None:
        result = self.make_backup()
        with self.assertRaises(WorkbenchError) as caught:
            self.backup.restore(
                archive_path=result["path"], target="relative/dir",
                operation=self.operation({"action": "restore"}),
            )
        self.assertEqual(caught.exception.code, INVALID_INPUT)


class MigrationTest(unittest.TestCase):
    def test_an_older_schema_migrates_and_a_newer_one_is_refused(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        # A minimal v1 database: only the migration ledger says version 1.
        old_db = base / "old.db"
        connection = sqlite3.connect(str(old_db))
        connection.execute(
            "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, "
            "applied_at TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (1, '2026-01-01')"
        )
        connection.commit()
        connection.close()
        # Opening it runs migrations 2..N forward.
        store = Store(old_db)
        try:
            self.assertEqual(store.schema_version(), SCHEMA_VERSION)
        finally:
            store.close()

        # A database claiming a newer schema is refused on open.
        future_db = base / "future.db"
        connection = sqlite3.connect(str(future_db))
        connection.execute(
            "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, "
            "applied_at TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, '2027-01-01')",
            (SCHEMA_VERSION + 5,),
        )
        connection.commit()
        connection.close()
        with self.assertRaises(WorkbenchError) as caught:
            Store(future_db)
        self.assertEqual(caught.exception.code, UNSUPPORTED)


if __name__ == "__main__":  # pragma: no cover - manual run
    unittest.main()
