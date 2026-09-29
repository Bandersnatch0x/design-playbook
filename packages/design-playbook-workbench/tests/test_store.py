#!/usr/bin/env python3
"""A01/R14: SQLite atomicity, migrations, and schema-version refusal.

The point of these tests is that a failure can never leave half a
registration behind, and that a database written by a newer runtime is
refused rather than silently opened.
"""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from design_playbook_workbench.errors import UNSUPPORTED, WorkbenchError
from design_playbook_workbench.store import (
    SCHEMA_VERSION,
    Store,
    WorkbenchDataDirectory,
    default_data_dir,
)


class DataDirectoryTest(unittest.TestCase):
    def test_ensure_creates_private_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            directory = WorkbenchDataDirectory(Path(tmp) / "data").ensure()
            for path in (
                directory.root,
                directory.blob_dir,
                directory.session_dir,
                directory.tmp_dir,
            ):
                self.assertTrue(path.is_dir(), path)
            self.assertFalse(directory.database_exists)
            self.assertEqual(
                directory.session_record_path,
                directory.session_dir / "session.json",
            )

    def test_default_data_dir_can_be_overridden_by_environment(self) -> None:
        chosen = default_data_dir({"DESIGN_PLAYBOOK_WORKBENCH_DATA_DIR": r"C:\x\y"})
        self.assertEqual(str(chosen), r"C:\x\y")


class MigrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name).resolve()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_fresh_database_reaches_the_current_schema(self) -> None:
        store = Store(self.base / "workbench.db")
        try:
            self.assertEqual(store.schema_version(), SCHEMA_VERSION)
            self.assertEqual(store.list_projects(), [])
            self.assertEqual(store.grants("missing"), [])
        finally:
            store.close()

    def test_reopening_is_idempotent(self) -> None:
        path = self.base / "workbench.db"
        first = Store(path)
        first.close()
        second = Store(path)
        try:
            self.assertEqual(second.schema_version(), SCHEMA_VERSION)
        finally:
            second.close()

    def test_newer_schema_is_refused_and_never_downgraded(self) -> None:
        path = self.base / "workbench.db"
        connection = sqlite3.connect(str(path))
        connection.execute(
            "CREATE TABLE schema_migrations ("
            "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
            (SCHEMA_VERSION + 5, "2099-01-01T00:00:00Z"),
        )
        connection.commit()
        connection.close()
        with self.assertRaises(WorkbenchError) as caught:
            Store(path)
        self.assertEqual(caught.exception.code, UNSUPPORTED)


class AtomicityTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name).resolve()
        self.store = Store(self.base / "workbench.db")

    def tearDown(self) -> None:
        self.store.close()
        self._tmp.cleanup()

    def test_project_and_binding_commit_together_or_not_at_all(self) -> None:
        project_id = self.store.create_project_with_binding(
            name="alpha",
            canonical_path=str(self.base / "alpha"),
            directory_identity="1:2",
            now="2026-09-26T10:00:00Z",
        )
        self.assertTrue(self.store.project_exists(project_id))
        binding = self.store.active_binding(project_id)
        self.assertEqual(binding["generation"], 1)
        self.assertEqual(binding["directory_identity"], "1:2")
        self.assertEqual(self.store.grants(project_id), ["read"])

    def test_failure_inside_the_transaction_leaves_no_project_row(self) -> None:
        with self.assertRaises(sqlite3.IntegrityError):
            # The binding insert violates NOT NULL, so the project insert
            # that preceded it must be rolled back with it.
            self.store.create_project_with_binding(
                name="half",
                canonical_path=str(self.base / "half"),
                directory_identity=None,  # type: ignore[arg-type]
                now="2026-09-26T10:00:00Z",
            )
        self.assertEqual(self.store.list_projects(), [])
        self.assertEqual(self.store.connection.execute(
            "SELECT COUNT(*) AS count FROM folder_bindings"
        ).fetchone()["count"], 0)

    def test_transaction_rolls_back_on_any_error(self) -> None:
        with self.assertRaises(RuntimeError):
            with self.store.transaction() as connection:
                connection.execute(
                    "INSERT INTO settings (key, value) VALUES ('a', 'b')"
                )
                raise RuntimeError("boom")
        self.assertIsNone(self.store.get_setting("a"))

    def test_rebind_adds_a_generation_and_switches_atomically(self) -> None:
        project_id = self.store.create_project_with_binding(
            name="alpha",
            canonical_path=str(self.base / "alpha"),
            directory_identity="1:2",
            now="2026-09-26T10:00:00Z",
        )
        generation = self.store.rebind_project(
            project_id=project_id,
            canonical_path=str(self.base / "beta"),
            directory_identity="3:4",
            now="2026-09-26T10:05:00Z",
        )
        self.assertEqual(generation, 2)
        active = self.store.active_binding(project_id)
        self.assertEqual(active["canonical_path"], str(self.base / "beta"))
        history = self.store.binding_history(project_id)
        self.assertEqual([row["generation"] for row in history], [1, 2])
        self.assertEqual(self.store.project(project_id)["counter"], 1)

    def test_binding_conflict_detects_path_or_identity_aliases(self) -> None:
        self.store.create_project_with_binding(
            name="alpha",
            canonical_path=str(self.base / "alpha"),
            directory_identity="1:2",
            now="2026-09-26T10:00:00Z",
        )
        by_path = self.store.binding_conflict(
            canonical_path=str(self.base / "alpha"),
            directory_identity="9:9",
            exclude_project_id=None,
        )
        self.assertIsNotNone(by_path)
        by_identity = self.store.binding_conflict(
            canonical_path=str(self.base / "elsewhere"),
            directory_identity="1:2",
            exclude_project_id=None,
        )
        self.assertIsNotNone(by_identity)
        excluded = self.store.binding_conflict(
            canonical_path=str(self.base / "alpha"),
            directory_identity="1:2",
            exclude_project_id=by_path["project_id"],
        )
        self.assertIsNone(excluded)

    def test_setting_round_trip(self) -> None:
        self.store.set_setting("currentProjectId", "abc")
        self.assertEqual(self.store.get_setting("currentProjectId"), "abc")
        self.store.clear_setting("currentProjectId")
        self.assertIsNone(self.store.get_setting("currentProjectId"))


if __name__ == "__main__":  # pragma: no cover - manual run
    unittest.main()
