"""Consistency backup, verified restore, and migration guard (R14).

A backup is a single sealed archive built from a consistency snapshot of the
SQLite database plus a fixed content-addressed blob manifest. Every hash is
verified as the package is written, the archive is finalized atomically (a
failed run leaves no "done" file), and the package deliberately excludes the
session record, live tokens, and the maintainer's source repository.

Restore is fail-closed and never overwrites the running data:

- the archive is validated first (no absolute paths, no ``..`` traversal, no
  symlink entries, bounded file count and uncompressed size, schema not newer
  than this runtime), and every blob and the database are hash-checked;
- content is extracted to a *new* data directory and its referential
  integrity is verified before anything is returned; the original data is
  left untouched and switching is a separate explicit step;
- restore never runs an Agent and never applies an incomplete apply journal;
  a restored directory carries no valid authorization, so grants and slash
  capabilities must be re-established.
"""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
import zipfile
from pathlib import Path
from typing import BinaryIO, Callable

from .blobs import BlobStore, digest_bytes
from .errors import (
    CONFLICT,
    CORRUPT_CONTENT,
    INVALID_INPUT,
    INVALID_TARGET,
    LIMIT_EXCEEDED,
    UNSUPPORTED,
    WorkbenchError,
)
from .service import Operation, WorkbenchService, utc_now
from .store import SCHEMA_VERSION, Store, WorkbenchDataDirectory

MANIFEST_NAME = "manifest.json"
DATABASE_ENTRY = "workbench.db"
BLOB_PREFIX = "blobs/"
BACKUP_FORMAT = "design-playbook-workbench-backup/v1"

MAX_RESTORE_BYTES = 20 * 1024 * 1024 * 1024  # 20 GiB
MAX_RESTORE_FILES = 100_000


def _hex_ok(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("sha256:")
        and len(value) == 71
        and all(c in "0123456789abcdef" for c in value[7:])
    )


class BackupService:
    """Create sealed backups, verify them, and restore to a new directory."""

    def __init__(
        self,
        *,
        store: Store,
        service: WorkbenchService,
        data_dir: WorkbenchDataDirectory,
        blobs: BlobStore,
        now_fn: Callable[[], str] | None = None,
    ) -> None:
        self.store = store
        self.service = service
        self.data_dir = data_dir
        self.blobs = blobs
        self._now = now_fn if now_fn is not None else utc_now

    # -- shared plumbing ------------------------------------------------

    def _record(self, operation: Operation, *, kind: str, result: dict, now: str) -> None:
        self.store.record_mutation(
            operation_id=operation.operation_id,
            entity_kind=kind,
            entity_id=result.get("backupId") or result.get("restoredDataDir") or kind,
            payload_digest=operation.digest,
            resulting_counter=0,
            result_json=json.dumps(result, ensure_ascii=False, sort_keys=True),
            project_id=None,
            now=now,
        )

    # -- create ---------------------------------------------------------

    def create(
        self, *, destination: object = None, overwrite: object = False, operation: Operation
    ) -> dict:
        """Seal a consistency snapshot + blob manifest into one archive."""
        replayed = self.service._replay(operation, kind="backup-create")
        if replayed is not None:
            return replayed
        backup_id = str(uuid.uuid4())
        now = self._now()
        target = self._resolve_destination(destination, backup_id, overwrite=overwrite)
        staging = self.data_dir.staging_dir / f"backup-{backup_id}"
        staging.mkdir(parents=True, exist_ok=True)
        db_snapshot = staging / DATABASE_ENTRY
        try:
            self._snapshot_database(db_snapshot)
            db_hash = digest_bytes(db_snapshot.read_bytes())
            blob_entries = self._blob_manifest()
            manifest = {
                "format": BACKUP_FORMAT,
                "schemaVersion": self.store.schema_version(),
                "runtimeSchemaVersion": SCHEMA_VERSION,
                "backupId": backup_id,
                "createdAt": now,
                "database": {"entry": DATABASE_ENTRY, "hash": db_hash,
                             "size": db_snapshot.stat().st_size},
                "blobs": blob_entries,
                "blobCount": len(blob_entries),
                "containsCredentials": False,
                "containsSourceRepo": False,
                "note": (
                    "备份含数据库一致性快照与内容寻址 blob 清单；不含 token、"
                    "有效授权或源仓库。恢复到新目录后需重新授权。"
                ),
            }
            partial = target.with_suffix(target.suffix + ".partial")
            try:
                stream = partial.open("xb")
            except FileExistsError:
                raise WorkbenchError(CONFLICT, detail="backup staging file already exists") from None
            try:
                with stream:
                    self._write_archive(stream, manifest, db_snapshot, blob_entries)
                if overwrite:
                    os.replace(partial, target)
                else:
                    # Atomic no-clobber publication also covers a concurrent creator.
                    os.link(partial, target)
            except FileExistsError:
                raise WorkbenchError(CONFLICT, detail="backup destination already exists") from None
            finally:
                partial.unlink(missing_ok=True)
        finally:
            self._cleanup(staging)
        result = {
            "backupId": backup_id,
            "path": str(target),
            "schemaVersion": manifest["schemaVersion"],
            "databaseHash": db_hash,
            "blobCount": len(blob_entries),
            "bytes": target.stat().st_size,
            "createdAt": now,
            "containsCredentials": False,
            "containsSourceRepo": False,
        }
        with self.store.transaction():
            self._record(operation, kind="backup-create", result=result, now=now)
        return {"result": result, "replayed": False, "counter": 0}

    def _storage_paths(self) -> list[Path]:
        """The live data the workbench owns; a backup never writes into it."""
        d = self.data_dir
        return [
            d.database_path,
            Path(str(d.database_path) + "-wal"),
            Path(str(d.database_path) + "-shm"),
            d.blob_dir,
            d.session_dir,
            d.tmp_dir,
            d.staging_dir,
        ]

    def _resolve_destination(
        self, destination: object, backup_id: str, *, overwrite: object = False
    ) -> Path:
        if not isinstance(overwrite, bool):
            raise WorkbenchError(INVALID_INPUT, detail="overwrite must be a boolean")
        if destination in (None, ""):
            destination = str(self.data_dir.root / "backups" / f"workbench-{backup_id}.dpwb.zip")
        if not isinstance(destination, str):
            raise WorkbenchError(INVALID_INPUT, detail="destination must be a path")
        path = Path(destination).expanduser()
        if not path.is_absolute():
            raise WorkbenchError(INVALID_INPUT, detail="destination must be absolute")
        # Never write a backup inside a registered source folder.
        for project in self.store.list_projects():
            binding = self.store.active_binding(project["project_id"])
            if binding is None:
                continue
            root = Path(binding["canonical_path"])
            try:
                path.resolve().relative_to(root.resolve())
            except ValueError:
                continue
            raise WorkbenchError(
                INVALID_TARGET, detail="a backup cannot be written inside a project folder"
            )
        # Never overwrite the workbench's own database, blobs, session,
        # temp, or staging storage -- a backup is written elsewhere.
        resolved = path.resolve()
        for owned in self._storage_paths():
            try:
                resolved.relative_to(owned.resolve())
            except ValueError:
                continue
            raise WorkbenchError(
                INVALID_TARGET,
                detail="a backup cannot be written into the workbench data storage",
            )
        if path.exists() and overwrite is not True:
            # The default uuid-named destination never collides; an explicit
            # path that already holds something needs a deliberate overwrite.
            raise WorkbenchError(
                CONFLICT, detail="destination already exists; pass overwrite to replace it"
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        return resolved

    def _snapshot_database(self, destination: Path) -> None:
        """A live, consistent copy via the SQLite backup API (WAL-safe)."""
        with self.store._lock:
            dest = sqlite3.connect(str(destination))
            try:
                self.store.connection.backup(dest)
            finally:
                dest.close()

    def _blob_manifest(self) -> list[dict]:
        entries: list[dict] = []
        for content_hash in sorted(self.blobs.iter_hashes()):
            data = self.blobs.read(content_hash)  # verifies the hash on read
            entries.append({"hash": content_hash, "size": len(data)})
        return entries

    def _write_archive(
        self, path: Path | BinaryIO, manifest: dict, db_snapshot: Path, blob_entries: list[dict]
    ) -> None:
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False, indent=2)
            )
            archive.write(db_snapshot, DATABASE_ENTRY)
            for entry in blob_entries:
                blob_path = self.blobs.path_for(entry["hash"])
                archive.write(blob_path, BLOB_PREFIX + entry["hash"])

    def _cleanup(self, staging: Path) -> None:
        try:
            for child in staging.glob("*"):
                child.unlink(missing_ok=True)
            staging.rmdir()
        except OSError:  # pragma: no cover - best-effort cleanup
            pass

    # -- verify ---------------------------------------------------------

    def verify(self, archive_path: object) -> dict:
        """Validate structure, schema, and every hash without extracting."""
        path = self._archive_path(archive_path)
        with zipfile.ZipFile(path, "r") as archive:
            self._reject_unsafe_entries(archive)
            manifest = self._read_manifest(archive)
            self._check_schema(manifest)
            db_bytes = archive.read(DATABASE_ENTRY)
            if digest_bytes(db_bytes) != manifest["database"]["hash"]:
                raise WorkbenchError(CORRUPT_CONTENT, detail="database hash mismatch")
            names = set(archive.namelist())
            for entry in manifest["blobs"]:
                name = BLOB_PREFIX + entry["hash"]
                if name not in names:
                    raise WorkbenchError(
                        CORRUPT_CONTENT, detail=f"missing blob: {entry['hash']}"
                    )
                if digest_bytes(archive.read(name)) != entry["hash"]:
                    raise WorkbenchError(
                        CORRUPT_CONTENT, detail=f"blob hash mismatch: {entry['hash']}"
                    )
        return {
            "path": str(path),
            "schemaVersion": manifest["schemaVersion"],
            "blobCount": manifest["blobCount"],
            "containsCredentials": manifest.get("containsCredentials", False),
            "containsSourceRepo": manifest.get("containsSourceRepo", False),
            "valid": True,
        }

    def _archive_path(self, archive_path: object) -> Path:
        if not isinstance(archive_path, str) or not archive_path:
            raise WorkbenchError(INVALID_INPUT, detail="archive path is required")
        path = Path(archive_path).expanduser()
        if not path.is_file():
            raise WorkbenchError(INVALID_TARGET, detail="archive not found")
        if not zipfile.is_zipfile(path):
            raise WorkbenchError(INVALID_INPUT, detail="not a backup archive")
        return path

    def _reject_unsafe_entries(self, archive: zipfile.ZipFile) -> None:
        total = 0
        infos = archive.infolist()
        if len(infos) > MAX_RESTORE_FILES:
            raise WorkbenchError(LIMIT_EXCEEDED, detail="too many entries in archive")
        for info in infos:
            name = info.filename
            if name.startswith("/") or name.startswith("\\") or ".." in Path(name).parts:
                # zip-slip: an entry that would escape the extraction root.
                raise WorkbenchError(INVALID_INPUT, detail="unsafe archive path")
            if (info.external_attr >> 16) & 0o170000 == 0o120000:
                # A symlink entry is never restored.
                raise WorkbenchError(INVALID_INPUT, detail="symlink entry rejected")
            total += info.file_size
            if total > MAX_RESTORE_BYTES:
                raise WorkbenchError(LIMIT_EXCEEDED, detail="uncompressed size exceeds limit")

    def _read_manifest(self, archive: zipfile.ZipFile) -> dict:
        try:
            manifest = json.loads(archive.read(MANIFEST_NAME).decode("utf-8"))
        except (KeyError, UnicodeDecodeError, json.JSONDecodeError):
            raise WorkbenchError(INVALID_INPUT, detail="manifest missing or invalid") from None
        if not isinstance(manifest, dict) or manifest.get("format") != BACKUP_FORMAT:
            raise WorkbenchError(INVALID_INPUT, detail="unknown backup format")
        database = manifest.get("database")
        if not isinstance(database, dict) or not _hex_ok(database.get("hash")):
            raise WorkbenchError(INVALID_INPUT, detail="database entry is invalid")
        blobs = manifest.get("blobs")
        if not isinstance(blobs, list) or not all(
            isinstance(item, dict) and _hex_ok(item.get("hash")) for item in blobs
        ):
            raise WorkbenchError(INVALID_INPUT, detail="blob manifest is invalid")
        manifest["blobCount"] = len(blobs)
        return manifest

    def _check_schema(self, manifest: dict) -> None:
        version = manifest.get("schemaVersion")
        if not isinstance(version, int) or version <= 0:
            raise WorkbenchError(INVALID_INPUT, detail="schema version is invalid")
        if version > SCHEMA_VERSION:
            # A backup from a newer runtime is never opened or downgraded.
            raise WorkbenchError(
                UNSUPPORTED, detail="backup schema is newer than this runtime"
            )

    # -- restore --------------------------------------------------------

    def restore(self, *, archive_path: object, target: object, operation: Operation) -> dict:
        """Restore a verified archive into a new data directory."""
        replayed = self.service._replay(operation, kind="backup-restore")
        if replayed is not None:
            return replayed
        verification = self.verify(archive_path)
        path = self._archive_path(archive_path)
        if not isinstance(target, str) or not target:
            raise WorkbenchError(INVALID_INPUT, detail="target directory is required")
        target_dir = Path(target).expanduser()
        if not target_dir.is_absolute():
            raise WorkbenchError(INVALID_INPUT, detail="target must be absolute")
        if target_dir.resolve() == self.data_dir.root.resolve():
            # Restore never overwrites the running data directory in place.
            raise WorkbenchError(
                CONFLICT, detail="restore target must differ from the active data directory"
            )
        if target_dir.exists() and any(target_dir.iterdir()):
            raise WorkbenchError(CONFLICT, detail="target directory must be empty")
        restored = WorkbenchDataDirectory(target_dir).ensure()
        now = self._now()
        with zipfile.ZipFile(path, "r") as archive:
            self._reject_unsafe_entries(archive)
            manifest = self._read_manifest(archive)
            self._check_schema(manifest)
            restored.database_path.write_bytes(archive.read(DATABASE_ENTRY))
            for entry in manifest["blobs"]:
                data = archive.read(BLOB_PREFIX + entry["hash"])
                if digest_bytes(data) != entry["hash"]:
                    raise WorkbenchError(CORRUPT_CONTENT, detail="blob hash mismatch")
                self._write_restored_blob(restored, entry["hash"], data)
        integrity = self._verify_referential_integrity(restored)
        result = {
            "restoredDataDir": str(restored.root),
            "schemaVersion": verification["schemaVersion"],
            "blobCount": verification["blobCount"],
            "integrity": integrity,
            "activeDataDir": str(self.data_dir.root),
            "switched": False,
            "reauthorizationRequired": True,
            "note": (
                "已恢复到新数据目录并校验引用完整性；原数据保留，切换为显式动作，"
                "恢复后需重新授权，且不会自动执行 Agent 或未完成的写回。"
            ),
        }
        with self.store.transaction():
            self._record(operation, kind="backup-restore", result=result, now=now)
        return {"result": result, "replayed": False, "counter": 0}

    def _write_restored_blob(
        self, restored: WorkbenchDataDirectory, content_hash: str, data: bytes
    ) -> None:
        blobs = BlobStore(restored.blob_dir)
        blobs.put(data, expected_hash=content_hash)

    def _verify_referential_integrity(self, restored: WorkbenchDataDirectory) -> dict:
        """Every referenced blob must be present in the restored directory."""
        store = Store(restored.database_path)
        try:
            blobs = BlobStore(restored.blob_dir)
            present = set(blobs.iter_hashes())
            missing: list[str] = []
            for manifest in store.all_revision_manifests():
                for entry in json.loads(manifest["manifest_json"]):
                    content_hash = entry.get("contentHash")
                    if content_hash and content_hash not in present:
                        missing.append(content_hash)
            incomplete_journal = store.incomplete_journal_count()
        finally:
            store.close()
        if missing:
            raise WorkbenchError(
                CORRUPT_CONTENT,
                detail=f"restored database references {len(missing)} missing blobs",
            )
        return {
            "referencedBlobsPresent": True,
            "incompleteJournals": incomplete_journal,
            "journalsNotReplayed": True,
        }


__all__ = [
    "BACKUP_FORMAT",
    "MAX_RESTORE_BYTES",
    "MAX_RESTORE_FILES",
    "BackupService",
]
