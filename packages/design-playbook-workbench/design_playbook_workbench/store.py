"""SQLite persistence and the workbench data directory (R01, R02, R14).

The workbench service is the single writer of its own state. Every
mutable operation runs inside one ``BEGIN IMMEDIATE`` transaction, so a
crash leaves either the complete change or none of it: a project row and
its folder binding are committed together, never half-written. The data
directory lives outside every imported source tree by construction
(``paths.validate_folder_target`` refuses the overlap), holds the
database, the content-addressed blob area, the credential record, and a
same-volume temporary area.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator

from .credentials import restrict_directory_to_current_user
from .errors import UNSUPPORTED, WorkbenchError

SCHEMA_VERSION = 8

_MIGRATIONS: dict[int, tuple[str, ...]] = {
    1: (
        """
        CREATE TABLE projects (
            project_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            archived INTEGER NOT NULL DEFAULT 0,
            counter INTEGER NOT NULL DEFAULT 0,
            current_binding_generation INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE folder_bindings (
            binding_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL
                REFERENCES projects(project_id) ON DELETE CASCADE,
            generation INTEGER NOT NULL,
            canonical_path TEXT NOT NULL,
            directory_identity TEXT NOT NULL,
            last_probed_at TEXT,
            last_known_state TEXT NOT NULL DEFAULT 'unknown',
            created_at TEXT NOT NULL,
            UNIQUE (project_id, generation)
        )
        """,
        """
        CREATE TABLE grants (
            project_id TEXT NOT NULL
                REFERENCES projects(project_id) ON DELETE CASCADE,
            scope TEXT NOT NULL,
            granted_at TEXT NOT NULL,
            PRIMARY KEY (project_id, scope)
        )
        """,
        """
        CREATE TABLE mutations (
            operation_id TEXT PRIMARY KEY,
            project_id TEXT,
            entity_kind TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            payload_digest TEXT NOT NULL,
            resulting_counter INTEGER,
            result_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """,
        """
        CREATE INDEX folder_bindings_identity_idx
            ON folder_bindings (directory_identity)
        """,
    ),
    2: (
        # WB-09: source change proposals, their persisted apply journal, and
        # the staged copies that make a partial multi-file write recoverable.
        # The journal is authoritative about what was attempted; the file
        # hashes decide what actually landed.
        """
        CREATE TABLE proposals (
            proposal_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL
                REFERENCES projects(project_id) ON DELETE CASCADE,
            binding_generation INTEGER NOT NULL,
            digest TEXT NOT NULL,
            state TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            staging_dir TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            applied_at TEXT,
            receipt_json TEXT
        )
        """,
        """
        CREATE INDEX proposals_project_idx
            ON proposals (project_id, created_at)
        """,
        """
        CREATE TABLE apply_journal (
            journal_id TEXT PRIMARY KEY,
            proposal_id TEXT NOT NULL,
            project_id TEXT NOT NULL,
            state TEXT NOT NULL,
            plan_json TEXT NOT NULL,
            done_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
        """
        CREATE UNIQUE INDEX apply_journal_proposal_idx
            ON apply_journal (proposal_id)
        """,
        """
        CREATE INDEX apply_journal_project_idx
            ON apply_journal (project_id, state)
        """,
    ),
    3: (
        # WB-03: assets, their mutable drafts, immutable revisions, and the
        # read-only import ledger. Revisions are immutable by construction:
        # publishing adds a row, it never edits one.
        """
        CREATE TABLE assets (
            asset_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL
                REFERENCES projects(project_id) ON DELETE CASCADE,
            kind TEXT NOT NULL,
            name TEXT NOT NULL,
            lifecycle TEXT NOT NULL DEFAULT 'draft',
            counter INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
        """
        CREATE INDEX assets_project_idx ON assets (project_id, kind, lifecycle)
        """,
        """
        CREATE TABLE asset_drafts (
            asset_id TEXT PRIMARY KEY
                REFERENCES assets(asset_id) ON DELETE CASCADE,
            revision_counter INTEGER NOT NULL DEFAULT 0,
            name TEXT NOT NULL,
            tags_json TEXT NOT NULL DEFAULT '[]',
            attributes_json TEXT NOT NULL DEFAULT '{}',
            updated_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE revisions (
            revision_id TEXT PRIMARY KEY,
            asset_id TEXT NOT NULL
                REFERENCES assets(asset_id) ON DELETE CASCADE,
            revision_number INTEGER NOT NULL,
            content_hash TEXT,
            carrier TEXT NOT NULL,
            capabilities_json TEXT NOT NULL DEFAULT '[]',
            dependencies_json TEXT NOT NULL DEFAULT '[]',
            source_locators_json TEXT NOT NULL DEFAULT '[]',
            manifest_json TEXT NOT NULL DEFAULT '[]',
            origin_json TEXT NOT NULL DEFAULT '{}',
            verified_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            UNIQUE (asset_id, revision_number)
        )
        """,
        """
        CREATE INDEX revisions_asset_idx ON revisions (asset_id, revision_number)
        """,
        """
        CREATE TABLE imports (
            import_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL
                REFERENCES projects(project_id) ON DELETE CASCADE,
            roots_json TEXT NOT NULL,
            status TEXT NOT NULL,
            file_count INTEGER NOT NULL,
            total_bytes INTEGER NOT NULL,
            warnings_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE import_files (
            import_id TEXT NOT NULL
                REFERENCES imports(import_id) ON DELETE CASCADE,
            relative_path TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            size INTEGER NOT NULL,
            media_type TEXT NOT NULL,
            carrier TEXT NOT NULL,
            PRIMARY KEY (import_id, relative_path)
        )
        """,
    ),
    4: (
        # WB-04: instances (a fixed revision used somewhere), the lineage
        # graph (derived-from / copied-from) and resolvable cross-project
        # import closures. A reference is a row, never an implicit "latest".
        """
        CREATE TABLE asset_lineage (
            child_asset_id TEXT NOT NULL
                REFERENCES assets(asset_id) ON DELETE CASCADE,
            parent_asset_id TEXT NOT NULL,
            parent_revision_id TEXT,
            relation TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (child_asset_id, relation)
        )
        """,
        """
        CREATE TABLE asset_dependencies (
            revision_id TEXT NOT NULL,
            depends_on_asset_id TEXT NOT NULL,
            depends_on_revision_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (revision_id, depends_on_asset_id)
        )
        """,
        """
        CREATE TABLE instances (
            instance_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL
                REFERENCES projects(project_id) ON DELETE CASCADE,
            asset_id TEXT NOT NULL,
            revision_id TEXT NOT NULL,
            overrides_json TEXT NOT NULL DEFAULT '{}',
            declared_public_params_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
        """
        CREATE INDEX instances_project_idx ON instances (project_id, asset_id)
        """,
        """
        CREATE INDEX instances_revision_idx ON instances (revision_id)
        """,
        """
        CREATE TABLE project_imports (
            import_closure_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL
                REFERENCES projects(project_id) ON DELETE CASCADE,
            source_project_id TEXT NOT NULL,
            source_asset_id TEXT NOT NULL,
            source_revision_id TEXT NOT NULL,
            mode TEXT NOT NULL,
            local_asset_id TEXT NOT NULL,
            local_revision_id TEXT,
            locators_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE upgrade_records (
            record_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            asset_id TEXT NOT NULL,
            from_revision_id TEXT NOT NULL,
            to_revision_id TEXT NOT NULL,
            instance_ids_json TEXT NOT NULL,
            kind TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """,
    ),
    5: (
        """
        CREATE TABLE canvases (
            canvas_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL
                REFERENCES projects(project_id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            counter INTEGER NOT NULL DEFAULT 0,
            document_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
        """
        CREATE INDEX canvases_project_idx ON canvases (project_id, updated_at)
        """,
        """
        CREATE TABLE canvas_transactions (
            canvas_id TEXT NOT NULL
                REFERENCES canvases(canvas_id) ON DELETE CASCADE,
            sequence INTEGER NOT NULL,
            undone INTEGER NOT NULL DEFAULT 0,
            transaction_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (canvas_id, sequence)
        )
        """,
        """
        CREATE INDEX canvas_transactions_idx
            ON canvas_transactions (canvas_id, sequence)
        """,
    ),
    6: (
        """
        CREATE TABLE scheme_snapshots (
            snapshot_id TEXT PRIMARY KEY,
            canvas_id TEXT NOT NULL
                REFERENCES canvases(canvas_id) ON DELETE CASCADE,
            project_id TEXT NOT NULL,
            board_id TEXT NOT NULL,
            board_name TEXT NOT NULL,
            counter INTEGER NOT NULL,
            content_hash TEXT NOT NULL,
            bytes INTEGER NOT NULL,
            node_count INTEGER NOT NULL,
            note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE INDEX scheme_snapshots_board_idx
            ON scheme_snapshots (canvas_id, board_id, created_at)
        """,
        """
        CREATE TABLE context_selections (
            selection_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL
                REFERENCES projects(project_id) ON DELETE CASCADE,
            canvas_id TEXT NOT NULL,
            board_id TEXT NOT NULL,
            canvas_counter INTEGER NOT NULL,
            state TEXT NOT NULL DEFAULT 'draft',
            payload_json TEXT NOT NULL,
            digest TEXT NOT NULL,
            confirmed_digest TEXT,
            confirmed_at TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
        """
        CREATE INDEX context_selections_project_idx
            ON context_selections (project_id, updated_at)
        """,
    ),
    7: (
        """
        CREATE TABLE work_requests (
            request_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL
                REFERENCES projects(project_id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            goal TEXT NOT NULL,
            target_stack TEXT NOT NULL,
            plan_json TEXT NOT NULL,
            allowed_actions_json TEXT NOT NULL,
            result_schema_json TEXT NOT NULL,
            context_selection_id TEXT NOT NULL,
            context_digest TEXT NOT NULL,
            binding_generation INTEGER NOT NULL,
            state TEXT NOT NULL,
            capability_id TEXT,
            handoff_command TEXT,
            expires_at TEXT,
            counter INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
        """
        CREATE INDEX work_requests_project_idx ON work_requests (project_id, updated_at)
        """,
        """
        CREATE TABLE work_attempts (
            attempt_id TEXT PRIMARY KEY,
            request_id TEXT NOT NULL
                REFERENCES work_requests(request_id) ON DELETE CASCADE,
            sequence INTEGER NOT NULL,
            state TEXT NOT NULL,
            lease_id TEXT,
            lease_expires_at TEXT,
            boot_id TEXT,
            capability_id TEXT,
            progress_json TEXT NOT NULL DEFAULT '{}',
            result_json TEXT,
            result_digest TEXT,
            proposal_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE (request_id, sequence)
        )
        """,
        """
        CREATE INDEX work_attempts_request_idx ON work_attempts (request_id, sequence)
        """,
    ),
    8: (
        """
        CREATE TABLE owner_confirmations (
            confirmation_id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL
                REFERENCES projects(project_id) ON DELETE CASCADE,
            run_id TEXT NOT NULL,
            object_type TEXT NOT NULL,
            object_id TEXT NOT NULL,
            source_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            note TEXT NOT NULL DEFAULT '',
            confirmed_by TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE INDEX owner_confirmations_object_idx
            ON owner_confirmations (project_id, run_id, object_type, object_id)
        """,
    ),
}

DEFAULT_DATA_DIR_NAME = "design-playbook-workbench"


def default_data_dir(environ: dict | None = None) -> Path:
    """The per-user data directory when the maintainer does not choose one."""
    env = os.environ if environ is None else environ
    override = env.get("DESIGN_PLAYBOOK_WORKBENCH_DATA_DIR")
    if override:
        return Path(override)
    if os.name == "nt":
        base = env.get("LOCALAPPDATA") or env.get("APPDATA")
        if base:
            return Path(base) / DEFAULT_DATA_DIR_NAME
    xdg = env.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / DEFAULT_DATA_DIR_NAME
    return Path.home() / ".local" / "share" / DEFAULT_DATA_DIR_NAME


class WorkbenchDataDirectory:
    """The one private working area, created and permission-narrowed once."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).expanduser()
        self.database_path = self.root / "workbench.db"
        self.blob_dir = self.root / "blobs"
        self.session_dir = self.root / "session"
        self.tmp_dir = self.root / "tmp"
        self.staging_dir = self.root / "staging"
        self.session_record_path = self.session_dir / "session.json"

    def ensure(self) -> "WorkbenchDataDirectory":
        for directory in (
            self.root,
            self.blob_dir,
            self.session_dir,
            self.tmp_dir,
            self.staging_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            for directory in (
                self.root,
                self.blob_dir,
                self.session_dir,
                self.tmp_dir,
                self.staging_dir,
            ):
                os.chmod(directory, 0o700)
        else:  # pragma: no cover - exercised on Windows CI
            restrict_directory_to_current_user(self.session_dir)
        return self

    @property
    def database_exists(self) -> bool:
        return self.database_path.exists()


class Store:
    """Thin, transaction-explicit SQLite access for the workbench domain."""

    def __init__(
        self,
        database_path: Path | str,
        *,
        now_fn: Callable[[], str] | None = None,
    ) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._now_fn = now_fn if now_fn is not None else _utc_now
        self._lock = threading.RLock()
        self._depth = 0
        self._connection = sqlite3.connect(
            str(self.database_path), isolation_level=None, check_same_thread=False
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA synchronous = FULL")
        self._connection.execute("PRAGMA busy_timeout = 5000")
        try:
            self._migrate()
        except BaseException:
            # A refused or failed migration must not leave the database
            # handle (and its file lock) dangling behind the exception.
            try:
                self._connection.close()
            except sqlite3.Error:  # pragma: no cover - defensive
                pass
            raise

    # -- lifecycle -----------------------------------------------------

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # -- transactions --------------------------------------------------

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """One immediate write transaction; nested use joins the outer one."""
        with self._lock:
            outermost = self._depth == 0
            if outermost:
                self._connection.execute("BEGIN IMMEDIATE")
            self._depth += 1
            try:
                yield self._connection
            except BaseException:
                self._depth -= 1
                if outermost:
                    try:
                        self._connection.execute("ROLLBACK")
                    except sqlite3.Error:  # pragma: no cover - defensive
                        pass
                raise
            else:
                self._depth -= 1
                if outermost:
                    self._connection.execute("COMMIT")

    @property
    def connection(self) -> sqlite3.Connection:
        return self._connection

    @contextmanager
    def read(self) -> Iterator[sqlite3.Connection]:
        """Serialize a read against the one connection (no transaction)."""
        with self._lock:
            yield self._connection

    def _migrate(self) -> None:
        with self._lock:
            self._connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            applied = {
                row["version"]
                for row in self._connection.execute(
                    "SELECT version FROM schema_migrations"
                )
            }
            newest = max(applied) if applied else 0
            if newest > SCHEMA_VERSION:
                # R14: a database from a newer runtime is never opened and
                # never downgraded.
                raise WorkbenchError(UNSUPPORTED)
            for version in sorted(_MIGRATIONS):
                if version in applied:
                    continue
                with self.transaction() as connection:
                    for statement in _MIGRATIONS[version]:
                        connection.execute(statement)
                    connection.execute(
                        "INSERT INTO schema_migrations (version, applied_at) "
                        "VALUES (?, ?)",
                        (version, self._now_fn()),
                    )

    def schema_version(self) -> int:
        with self.read() as connection:
            row = connection.execute(
                "SELECT MAX(version) AS version FROM schema_migrations"
            ).fetchone()
            return int(row["version"] or 0)

    # -- settings ------------------------------------------------------

    def set_setting(self, key: str, value: str) -> None:
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def get_setting(self, key: str) -> str | None:
        with self.read() as connection:
            row = connection.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
            return row["value"] if row is not None else None

    def clear_setting(self, key: str) -> None:
        with self.transaction() as connection:
            connection.execute("DELETE FROM settings WHERE key = ?", (key,))

    # -- projects and bindings -----------------------------------------

    def create_project_with_binding(
        self,
        *,
        name: str,
        canonical_path: str,
        directory_identity: str,
        now: str,
    ) -> str:
        """Project row and its first binding, committed as one transaction.

        A failure between the two inserts rolls both back, so a crash can
        never leave a half-registered project with no folder binding (A01).
        """
        project_id = str(uuid.uuid4())
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO projects (project_id, name, archived, counter, "
                "current_binding_generation, created_at, updated_at) "
                "VALUES (?, ?, 0, 0, 1, ?, ?)",
                (project_id, name, now, now),
            )
            self._insert_binding(
                connection,
                project_id=project_id,
                generation=1,
                canonical_path=canonical_path,
                directory_identity=directory_identity,
                now=now,
            )
            connection.execute(
                "INSERT INTO grants (project_id, scope, granted_at) VALUES (?, ?, ?)",
                (project_id, "read", now),
            )
        return project_id

    def rebind_project(
        self,
        *,
        project_id: str,
        canonical_path: str,
        directory_identity: str,
        now: str,
    ) -> int:
        """Add a new binding generation and switch to it atomically."""
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT MAX(generation) AS generation FROM folder_bindings "
                "WHERE project_id = ?",
                (project_id,),
            ).fetchone()
            generation = int(row["generation"] or 0) + 1
            self._insert_binding(
                connection,
                project_id=project_id,
                generation=generation,
                canonical_path=canonical_path,
                directory_identity=directory_identity,
                now=now,
            )
            connection.execute(
                "UPDATE projects SET current_binding_generation = ?, "
                "counter = counter + 1, updated_at = ? WHERE project_id = ?",
                (generation, now, project_id),
            )
            return generation

    @staticmethod
    def _insert_binding(
        connection: sqlite3.Connection,
        *,
        project_id: str,
        generation: int,
        canonical_path: str,
        directory_identity: str,
        now: str,
    ) -> None:
        connection.execute(
            "INSERT INTO folder_bindings (binding_id, project_id, generation, "
            "canonical_path, directory_identity, last_probed_at, "
            "last_known_state, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                str(uuid.uuid4()),
                project_id,
                generation,
                canonical_path,
                directory_identity,
                now,
                "connected",
                now,
            ),
        )

    def project(self, project_id: str) -> dict:
        with self.read() as connection:
            row = connection.execute(
                "SELECT * FROM projects WHERE project_id = ?", (project_id,)
            ).fetchone()
            if row is None:
                raise KeyError(project_id)
            return dict(row)

    def project_exists(self, project_id: str) -> bool:
        with self.read() as connection:
            row = connection.execute(
                "SELECT 1 AS present FROM projects WHERE project_id = ?",
                (project_id,),
            ).fetchone()
            return row is not None

    def list_projects(self) -> list[dict]:
        with self.read() as connection:
            rows = connection.execute(
                "SELECT * FROM projects ORDER BY created_at ASC, project_id ASC"
            ).fetchall()
            return [dict(row) for row in rows]

    def active_binding(self, project_id: str) -> dict | None:
        with self.read() as connection:
            row = connection.execute(
                "SELECT b.* FROM folder_bindings AS b "
                "JOIN projects AS p ON p.project_id = b.project_id "
                "WHERE b.project_id = ? AND b.generation = p.current_binding_generation",
                (project_id,),
            ).fetchone()
            return dict(row) if row is not None else None

    def binding_history(self, project_id: str) -> list[dict]:
        with self.read() as connection:
            rows = connection.execute(
                "SELECT * FROM folder_bindings WHERE project_id = ? "
                "ORDER BY generation ASC",
                (project_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def binding_conflict(
        self, *, canonical_path: str, directory_identity: str, exclude_project_id: str | None
    ) -> dict | None:
        """An existing *current* binding on the same path or same identity."""
        with self.read() as connection:
            rows = connection.execute(
                "SELECT b.* FROM folder_bindings AS b "
                "JOIN projects AS p ON p.project_id = b.project_id "
                "WHERE b.generation = p.current_binding_generation "
                "AND (b.canonical_path = ? OR b.directory_identity = ?)",
                (canonical_path, directory_identity),
            ).fetchall()
            for row in rows:
                row = dict(row)
                if (
                    exclude_project_id is not None
                    and row["project_id"] == exclude_project_id
                ):
                    continue
                return row
            return None

    def touch_binding_state(
        self, *, binding_id: str, state: str, probed_at: str
    ) -> None:
        with self.transaction() as connection:
            connection.execute(
                "UPDATE folder_bindings SET last_known_state = ?, last_probed_at = ? "
                "WHERE binding_id = ?",
                (state, probed_at, binding_id),
            )

    def rename_project(self, *, project_id: str, name: str, now: str) -> int:
        with self.transaction() as connection:
            cursor = connection.execute(
                "UPDATE projects SET name = ?, counter = counter + 1, updated_at = ? "
                "WHERE project_id = ?",
                (name, now, project_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(project_id)
            row = connection.execute(
                "SELECT counter FROM projects WHERE project_id = ?", (project_id,)
            ).fetchone()
            return int(row["counter"])

    def set_archived(self, *, project_id: str, archived: bool, now: str) -> int:
        with self.transaction() as connection:
            cursor = connection.execute(
                "UPDATE projects SET archived = ?, counter = counter + 1, "
                "updated_at = ? WHERE project_id = ?",
                (1 if archived else 0, now, project_id),
            )
            if cursor.rowcount == 0:
                raise KeyError(project_id)
            row = connection.execute(
                "SELECT counter FROM projects WHERE project_id = ?", (project_id,)
            ).fetchone()
            return int(row["counter"])

    def delete_project(self, project_id: str) -> None:
        with self.transaction() as connection:
            connection.execute(
                "DELETE FROM projects WHERE project_id = ?", (project_id,)
            )

    # -- grants --------------------------------------------------------

    def set_grants(
        self, *, project_id: str, scopes: list[str], now: str
    ) -> int:
        with self.transaction() as connection:
            connection.execute(
                "DELETE FROM grants WHERE project_id = ?", (project_id,)
            )
            for scope in scopes:
                connection.execute(
                    "INSERT INTO grants (project_id, scope, granted_at) VALUES (?, ?, ?)",
                    (project_id, scope, now),
                )
            connection.execute(
                "UPDATE projects SET counter = counter + 1, updated_at = ? "
                "WHERE project_id = ?",
                (now, project_id),
            )
            row = connection.execute(
                "SELECT counter FROM projects WHERE project_id = ?", (project_id,)
            ).fetchone()
            return int(row["counter"])

    def grants(self, project_id: str) -> list[str]:
        with self.read() as connection:
            rows = connection.execute(
                "SELECT scope FROM grants WHERE project_id = ? ORDER BY scope ASC",
                (project_id,),
            ).fetchall()
            return [row["scope"] for row in rows]

    # -- assets, drafts, revisions, imports (WB-03) ---------------------

    def create_asset(
        self,
        *,
        asset_id: str,
        project_id: str,
        kind: str,
        name: str,
        tags: list[str],
        attributes: dict,
        now: str,
    ) -> None:
        """Asset plus its first draft row, committed as one transaction."""
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO assets (asset_id, project_id, kind, name, lifecycle, "
                "counter, created_at, updated_at) VALUES (?, ?, ?, ?, 'draft', 0, ?, ?)",
                (asset_id, project_id, kind, name, now, now),
            )
            connection.execute(
                "INSERT INTO asset_drafts (asset_id, revision_counter, name, "
                "tags_json, attributes_json, updated_at) VALUES (?, 0, ?, ?, ?, ?)",
                (
                    asset_id,
                    name,
                    _json(tags),
                    _json(attributes),
                    now,
                ),
            )

    def asset(self, asset_id: str) -> dict | None:
        with self.read() as connection:
            row = connection.execute(
                "SELECT * FROM assets WHERE asset_id = ?", (asset_id,)
            ).fetchone()
            return dict(row) if row is not None else None

    def draft(self, asset_id: str) -> dict | None:
        with self.read() as connection:
            row = connection.execute(
                "SELECT * FROM asset_drafts WHERE asset_id = ?", (asset_id,)
            ).fetchone()
            return dict(row) if row is not None else None

    def project_assets(self, project_id: str) -> list[dict]:
        with self.read() as connection:
            rows = connection.execute(
                "SELECT * FROM assets WHERE project_id = ? "
                "ORDER BY created_at ASC, rowid ASC",
                (project_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def set_asset_lifecycle(
        self, *, asset_id: str, lifecycle: str, now: str
    ) -> int:
        with self.transaction() as connection:
            connection.execute(
                "UPDATE assets SET lifecycle = ?, counter = counter + 1, "
                "updated_at = ? WHERE asset_id = ?",
                (lifecycle, now, asset_id),
            )
            row = connection.execute(
                "SELECT counter FROM assets WHERE asset_id = ?", (asset_id,)
            ).fetchone()
            return int(row["counter"]) if row is not None else 0

    def rename_asset(self, *, asset_id: str, name: str, now: str) -> int:
        with self.transaction() as connection:
            connection.execute(
                "UPDATE assets SET name = ?, counter = counter + 1, updated_at = ? "
                "WHERE asset_id = ?",
                (name, now, asset_id),
            )
            connection.execute(
                "UPDATE asset_drafts SET name = ?, updated_at = ? WHERE asset_id = ?",
                (name, now, asset_id),
            )
            row = connection.execute(
                "SELECT counter FROM assets WHERE asset_id = ?", (asset_id,)
            ).fetchone()
            return int(row["counter"]) if row is not None else 0

    def update_draft(
        self, *, asset_id: str, tags: list[str], attributes: dict, now: str
    ) -> None:
        with self.transaction() as connection:
            connection.execute(
                "UPDATE asset_drafts SET tags_json = ?, attributes_json = ?, "
                "updated_at = ? WHERE asset_id = ?",
                (_json(tags), _json(attributes), now, asset_id),
            )

    def bump_asset_counter(self, *, asset_id: str, now: str) -> int:
        with self.transaction() as connection:
            connection.execute(
                "UPDATE assets SET counter = counter + 1, updated_at = ? "
                "WHERE asset_id = ?",
                (now, asset_id),
            )
            row = connection.execute(
                "SELECT counter FROM assets WHERE asset_id = ?", (asset_id,)
            ).fetchone()
            return int(row["counter"]) if row is not None else 0

    def insert_revision(
        self,
        *,
        revision_id: str,
        asset_id: str,
        revision_number: int,
        content_hash: str | None,
        carrier: str,
        capabilities: list[str],
        dependencies: list[dict],
        source_locators: list[dict],
        manifest: list[dict],
        origin: dict,
        verified: list[dict] | None = None,
        now: str,
    ) -> None:
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO revisions (revision_id, asset_id, revision_number, "
                "content_hash, carrier, capabilities_json, dependencies_json, "
                "source_locators_json, manifest_json, origin_json, verified_json, "
                "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    revision_id,
                    asset_id,
                    revision_number,
                    content_hash,
                    carrier,
                    _json(capabilities),
                    _json(dependencies),
                    _json(source_locators),
                    _json(manifest),
                    _json(origin),
                    _json(verified or []),
                    now,
                ),
            )
            connection.execute(
                "UPDATE asset_drafts SET revision_counter = ?, updated_at = ? "
                "WHERE asset_id = ?",
                (revision_number, now, asset_id),
            )
            connection.execute(
                "UPDATE assets SET lifecycle = CASE WHEN lifecycle = 'draft' "
                "THEN 'published' ELSE lifecycle END, counter = counter + 1, "
                "updated_at = ? WHERE asset_id = ?",
                (now, asset_id),
            )

    def latest_revision(self, asset_id: str) -> dict | None:
        with self.read() as connection:
            row = connection.execute(
                "SELECT * FROM revisions WHERE asset_id = ? "
                "ORDER BY revision_number DESC LIMIT 1",
                (asset_id,),
            ).fetchone()
            return dict(row) if row is not None else None

    def revision(self, revision_id: str) -> dict | None:
        with self.read() as connection:
            row = connection.execute(
                "SELECT * FROM revisions WHERE revision_id = ?", (revision_id,)
            ).fetchone()
            return dict(row) if row is not None else None

    def asset_revisions(self, asset_id: str) -> list[dict]:
        with self.read() as connection:
            rows = connection.execute(
                "SELECT * FROM revisions WHERE asset_id = ? "
                "ORDER BY revision_number ASC",
                (asset_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def create_import(
        self,
        *,
        import_id: str,
        project_id: str,
        roots: list[str],
        status: str,
        file_count: int,
        total_bytes: int,
        warnings: list[str],
        now: str,
    ) -> None:
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO imports (import_id, project_id, roots_json, status, "
                "file_count, total_bytes, warnings_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    import_id,
                    project_id,
                    _json(roots),
                    status,
                    file_count,
                    total_bytes,
                    _json(warnings),
                    now,
                ),
            )

    def add_import_file(
        self,
        *,
        import_id: str,
        relative_path: str,
        content_hash: str,
        size: int,
        media_type: str,
        carrier: str,
    ) -> None:
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO import_files (import_id, relative_path, content_hash, "
                "size, media_type, carrier) VALUES (?, ?, ?, ?, ?, ?)",
                (import_id, relative_path, content_hash, size, media_type, carrier),
            )

    def import_record(self, import_id: str) -> dict | None:
        with self.read() as connection:
            row = connection.execute(
                "SELECT * FROM imports WHERE import_id = ?", (import_id,)
            ).fetchone()
            return dict(row) if row is not None else None

    def all_import_files(self) -> list[dict]:
        with self.read() as connection:
            rows = connection.execute(
                "SELECT * FROM import_files ORDER BY import_id, relative_path"
            ).fetchall()
            return [dict(row) for row in rows]

    def all_revision_manifests(self) -> list[dict]:
        with self.read() as connection:
            rows = connection.execute(
                "SELECT revision_id, manifest_json FROM revisions"
            ).fetchall()
            return [dict(row) for row in rows]

    # -- instances, lineage, dependencies, closures (WB-04) ------------

    def add_lineage(
        self,
        *,
        child_asset_id: str,
        parent_asset_id: str,
        parent_revision_id: str | None,
        relation: str,
        now: str,
    ) -> None:
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO asset_lineage (child_asset_id, parent_asset_id, "
                "parent_revision_id, relation, created_at) VALUES (?, ?, ?, ?, ?)",
                (child_asset_id, parent_asset_id, parent_revision_id, relation, now),
            )

    def lineage(self, child_asset_id: str) -> list[dict]:
        with self.read() as connection:
            rows = connection.execute(
                "SELECT * FROM asset_lineage WHERE child_asset_id = ? "
                "ORDER BY relation ASC",
                (child_asset_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def insert_dependencies(
        self,
        *,
        revision_id: str,
        dependencies: list[dict],
        now: str,
    ) -> None:
        with self.transaction() as connection:
            for dependency in dependencies:
                connection.execute(
                    "INSERT INTO asset_dependencies (revision_id, "
                    "depends_on_asset_id, depends_on_revision_id, created_at) "
                    "VALUES (?, ?, ?, ?)",
                    (
                        revision_id,
                        dependency["assetId"],
                        dependency["revisionId"],
                        now,
                    ),
                )

    def dependencies(self, revision_id: str) -> list[dict]:
        with self.read() as connection:
            rows = connection.execute(
                "SELECT * FROM asset_dependencies WHERE revision_id = ? "
                "ORDER BY depends_on_asset_id ASC",
                (revision_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def insert_instance(
        self,
        *,
        instance_id: str,
        project_id: str,
        asset_id: str,
        revision_id: str,
        overrides: dict,
        declared_public_params: list,
        now: str,
    ) -> None:
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO instances (instance_id, project_id, asset_id, "
                "revision_id, overrides_json, declared_public_params_json, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    instance_id,
                    project_id,
                    asset_id,
                    revision_id,
                    _json(overrides),
                    _json(declared_public_params),
                    now,
                    now,
                ),
            )

    def instance(self, instance_id: str) -> dict | None:
        with self.read() as connection:
            row = connection.execute(
                "SELECT * FROM instances WHERE instance_id = ?", (instance_id,)
            ).fetchone()
            return dict(row) if row is not None else None

    def project_instances(self, project_id: str) -> list[dict]:
        with self.read() as connection:
            rows = connection.execute(
                "SELECT * FROM instances WHERE project_id = ? "
                "ORDER BY created_at ASC, rowid ASC",
                (project_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def asset_instances(self, asset_id: str) -> list[dict]:
        with self.read() as connection:
            rows = connection.execute(
                "SELECT * FROM instances WHERE asset_id = ? "
                "ORDER BY created_at ASC, rowid ASC",
                (asset_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def revision_instances(self, revision_id: str) -> list[dict]:
        with self.read() as connection:
            rows = connection.execute(
                "SELECT * FROM instances WHERE revision_id = ?", (revision_id,)
            ).fetchall()
            return [dict(row) for row in rows]

    def set_instance_revision(
        self,
        *,
        instance_id: str,
        revision_id: str,
        overrides: dict,
        now: str,
    ) -> None:
        with self.transaction() as connection:
            connection.execute(
                "UPDATE instances SET revision_id = ?, overrides_json = ?, "
                "updated_at = ? WHERE instance_id = ?",
                (revision_id, _json(overrides), now, instance_id),
            )

    def delete_instance(self, instance_id: str) -> None:
        with self.transaction() as connection:
            connection.execute(
                "DELETE FROM instances WHERE instance_id = ?", (instance_id,)
            )

    # -- reference scanning and hard delete (WB-12) ---------------------

    def assets_depending_on_asset(self, asset_id: str) -> list[dict]:
        """Published revisions (of other assets) that declare this dependency."""
        with self.read() as connection:
            rows = connection.execute(
                "SELECT d.revision_id, d.depends_on_revision_id, r.asset_id, "
                "r.revision_number, a.name, a.kind, a.project_id "
                "FROM asset_dependencies d "
                "JOIN revisions r ON r.revision_id = d.revision_id "
                "JOIN assets a ON a.asset_id = r.asset_id "
                "WHERE d.depends_on_asset_id = ?",
                (asset_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def lineage_children(self, parent_asset_id: str) -> list[dict]:
        """Assets derived from or copied from this asset."""
        with self.read() as connection:
            rows = connection.execute(
                "SELECT l.child_asset_id, l.relation, a.name, a.kind, a.project_id "
                "FROM asset_lineage l "
                "JOIN assets a ON a.asset_id = l.child_asset_id "
                "WHERE l.parent_asset_id = ?",
                (parent_asset_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def import_copies_of_source(self, source_asset_id: str) -> list[dict]:
        """Cross-project closures that copied/referenced this source asset."""
        with self.read() as connection:
            rows = connection.execute(
                "SELECT import_closure_id, project_id, local_asset_id, mode, "
                "created_at FROM project_imports WHERE source_asset_id = ?",
                (source_asset_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def import_closures_local(self, local_asset_id: str) -> list[dict]:
        with self.read() as connection:
            rows = connection.execute(
                "SELECT import_closure_id, project_id, source_project_id, "
                "source_asset_id, mode FROM project_imports WHERE local_asset_id = ?",
                (local_asset_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def delete_asset(self, asset_id: str) -> None:
        """Hard-delete an asset and every workbench row that hangs off it.

        Revisions, drafts, and child-lineage rows cascade; the rows that
        reference the asset by value (dependencies as a target, lineage as a
        parent, cross-project closures, upgrade records, instances) are
        removed here so no dangling reference survives.
        """
        with self.transaction() as connection:
            revision_ids = [
                row["revision_id"]
                for row in connection.execute(
                    "SELECT revision_id FROM revisions WHERE asset_id = ?", (asset_id,)
                ).fetchall()
            ]
            connection.execute(
                "DELETE FROM instances WHERE asset_id = ?", (asset_id,)
            )
            connection.execute(
                "DELETE FROM asset_dependencies WHERE depends_on_asset_id = ?",
                (asset_id,),
            )
            for revision_id in revision_ids:
                connection.execute(
                    "DELETE FROM asset_dependencies WHERE revision_id = ?",
                    (revision_id,),
                )
            connection.execute(
                "DELETE FROM asset_lineage WHERE parent_asset_id = ?", (asset_id,)
            )
            connection.execute(
                "DELETE FROM upgrade_records WHERE asset_id = ?", (asset_id,)
            )
            connection.execute(
                "DELETE FROM project_imports WHERE local_asset_id = ?", (asset_id,)
            )
            # The asset row (and its cascading revisions/drafts/child lineage)
            # goes last so the reads above still resolve.
            connection.execute(
                "DELETE FROM assets WHERE asset_id = ?", (asset_id,)
            )

    def revisions_by_ids(self, revision_ids: list[str]) -> list[dict]:
        if not revision_ids:
            return []
        placeholders = ",".join("?" for _ in revision_ids)
        with self.read() as connection:
            rows = connection.execute(
                f"SELECT * FROM revisions WHERE revision_id IN ({placeholders})",
                tuple(revision_ids),
            ).fetchall()
            return [dict(row) for row in rows]

    def insert_import_closure(
        self,
        *,
        import_closure_id: str,
        project_id: str,
        source_project_id: str,
        source_asset_id: str,
        source_revision_id: str,
        mode: str,
        local_asset_id: str,
        local_revision_id: str | None,
        locators: list[dict],
        now: str,
    ) -> None:
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO project_imports (import_closure_id, project_id, "
                "source_project_id, source_asset_id, source_revision_id, mode, "
                "local_asset_id, local_revision_id, locators_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    import_closure_id,
                    project_id,
                    source_project_id,
                    source_asset_id,
                    source_revision_id,
                    mode,
                    local_asset_id,
                    local_revision_id,
                    _json(locators),
                    now,
                ),
            )

    def project_import_closures(self, project_id: str) -> list[dict]:
        with self.read() as connection:
            rows = connection.execute(
                "SELECT * FROM project_imports WHERE project_id = ? "
                "ORDER BY created_at ASC, rowid ASC",
                (project_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def import_closure_by_local_asset(self, local_asset_id: str) -> dict | None:
        with self.read() as connection:
            row = connection.execute(
                "SELECT * FROM project_imports WHERE local_asset_id = ? "
                "ORDER BY created_at ASC LIMIT 1",
                (local_asset_id,),
            ).fetchone()
            return dict(row) if row is not None else None

    def insert_upgrade_record(
        self,
        *,
        record_id: str,
        project_id: str,
        asset_id: str,
        from_revision_id: str,
        to_revision_id: str,
        instance_ids: list[str],
        kind: str,
        now: str,
    ) -> None:
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO upgrade_records (record_id, project_id, asset_id, "
                "from_revision_id, to_revision_id, instance_ids_json, kind, "
                "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record_id,
                    project_id,
                    asset_id,
                    from_revision_id,
                    to_revision_id,
                    _json(instance_ids),
                    kind,
                    now,
                ),
            )

    def asset_upgrade_records(self, asset_id: str) -> list[dict]:
        with self.read() as connection:
            rows = connection.execute(
                "SELECT * FROM upgrade_records WHERE asset_id = ? "
                "ORDER BY created_at ASC, rowid ASC",
                (asset_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    # -- proposals and the apply journal (WB-09) -----------------------

    def create_proposal(
        self,
        *,
        proposal_id: str,
        project_id: str,
        binding_generation: int,
        digest: str,
        payload_json: str,
        staging_dir: str,
        expires_at: str,
        now: str,
    ) -> str:
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO proposals (proposal_id, project_id, "
                "binding_generation, digest, state, payload_json, staging_dir, "
                "created_at, expires_at, applied_at, receipt_json) "
                "VALUES (?, ?, ?, ?, 'awaiting-authorization', ?, ?, ?, ?, NULL, NULL)",
                (
                    proposal_id,
                    project_id,
                    binding_generation,
                    digest,
                    payload_json,
                    staging_dir,
                    now,
                    expires_at,
                ),
            )
        return proposal_id

    def proposal(self, proposal_id: str) -> dict | None:
        with self.read() as connection:
            row = connection.execute(
                "SELECT * FROM proposals WHERE proposal_id = ?", (proposal_id,)
            ).fetchone()
            return dict(row) if row is not None else None

    def project_proposals(self, project_id: str) -> list[dict]:
        with self.read() as connection:
            # Newest first, with insertion order as the tie-break: proposals
            # created within the same second must still have a stable order.
            rows = connection.execute(
                "SELECT * FROM proposals WHERE project_id = ? "
                "ORDER BY created_at DESC, rowid DESC",
                (project_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def set_proposal_state(
        self,
        *,
        proposal_id: str,
        state: str,
        now: str,
        receipt_json: str | None = None,
        applied_at: str | None = None,
    ) -> None:
        with self.transaction() as connection:
            connection.execute(
                "UPDATE proposals SET state = ?, receipt_json = COALESCE(?, receipt_json), "
                "applied_at = COALESCE(?, applied_at) WHERE proposal_id = ?",
                (state, receipt_json, applied_at, proposal_id),
            )

    def create_journal(
        self,
        *,
        proposal_id: str,
        project_id: str,
        state: str,
        plan_json: str,
        now: str,
    ) -> str:
        journal_id = str(uuid.uuid4())
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO apply_journal (journal_id, proposal_id, project_id, "
                "state, plan_json, done_json, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, '[]', ?, ?)",
                (journal_id, proposal_id, project_id, state, plan_json, now, now),
            )
        return journal_id

    def journal(self, proposal_id: str) -> dict | None:
        with self.read() as connection:
            row = connection.execute(
                "SELECT * FROM apply_journal WHERE proposal_id = ?", (proposal_id,)
            ).fetchone()
            return dict(row) if row is not None else None

    def incomplete_journal(self, project_id: str) -> dict | None:
        """The one journal that must block new writes for this project."""
        with self.read() as connection:
            row = connection.execute(
                "SELECT * FROM apply_journal WHERE project_id = ? "
                "AND state IN ('writing', 'recovery-required') "
                "ORDER BY created_at ASC LIMIT 1",
                (project_id,),
            ).fetchone()
            return dict(row) if row is not None else None

    def incomplete_journal_count(self) -> int:
        """How many apply journals are mid-write across every project.

        A restored database keeps these rows so the recovery UI can act on
        them; the restore path never replays them automatically.
        """
        with self.read() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS n FROM apply_journal "
                "WHERE state IN ('writing', 'recovery-required')"
            ).fetchone()
            return int(row["n"]) if row is not None else 0

    def set_journal_state(
        self, *, journal_id: str, state: str, done_json: str, now: str
    ) -> None:
        with self.transaction() as connection:
            connection.execute(
                "UPDATE apply_journal SET state = ?, done_json = ?, updated_at = ? "
                "WHERE journal_id = ?",
                (state, done_json, now, journal_id),
            )

    # -- canvases ------------------------------------------------------

    def create_canvas(
        self,
        *,
        canvas_id: str,
        project_id: str,
        name: str,
        document: dict,
        now: str,
    ) -> None:
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO canvases (canvas_id, project_id, name, counter, "
                "document_json, created_at, updated_at) VALUES (?, ?, ?, 0, ?, ?, ?)",
                (canvas_id, project_id, name, _json(document), now, now),
            )

    def canvas(self, canvas_id: str) -> dict | None:
        with self.read() as connection:
            row = connection.execute(
                "SELECT * FROM canvases WHERE canvas_id = ?", (canvas_id,)
            ).fetchone()
            return dict(row) if row is not None else None

    def project_canvases(self, project_id: str) -> list[dict]:
        with self.read() as connection:
            rows = connection.execute(
                "SELECT * FROM canvases WHERE project_id = ? "
                "ORDER BY updated_at DESC, rowid DESC",
                (project_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def save_canvas(
        self,
        *,
        canvas_id: str,
        document: dict,
        name: str | None = None,
        bump: int = 1,
        now: str,
    ) -> int:
        """Write the document and advance the canvas counter."""
        with self.transaction() as connection:
            if name is None:
                connection.execute(
                    "UPDATE canvases SET document_json = ?, "
                    "counter = counter + ?, updated_at = ? WHERE canvas_id = ?",
                    (_json(document), bump, now, canvas_id),
                )
            else:
                connection.execute(
                    "UPDATE canvases SET document_json = ?, name = ?, "
                    "counter = counter + ?, updated_at = ? WHERE canvas_id = ?",
                    (_json(document), name, bump, now, canvas_id),
                )
            row = connection.execute(
                "SELECT counter FROM canvases WHERE canvas_id = ?", (canvas_id,)
            ).fetchone()
            return int(row["counter"])

    def delete_canvas(self, canvas_id: str) -> None:
        with self.transaction() as connection:
            connection.execute(
                "DELETE FROM canvases WHERE canvas_id = ?", (canvas_id,)
            )

    def append_canvas_transaction(
        self, *, canvas_id: str, transaction: dict, now: str
    ) -> int:
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) AS sequence FROM "
                "canvas_transactions WHERE canvas_id = ?",
                (canvas_id,),
            ).fetchone()
            sequence = int(row["sequence"]) + 1
            connection.execute(
                "INSERT INTO canvas_transactions (canvas_id, sequence, undone, "
                "transaction_json, created_at) VALUES (?, ?, 0, ?, ?)",
                (canvas_id, sequence, _json(transaction), now),
            )
            return sequence

    def canvas_transactions(self, canvas_id: str) -> list[dict]:
        with self.read() as connection:
            rows = connection.execute(
                "SELECT * FROM canvas_transactions WHERE canvas_id = ? "
                "ORDER BY sequence ASC",
                (canvas_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def set_canvas_transaction_undone(
        self, *, canvas_id: str, sequence: int, undone: bool
    ) -> None:
        with self.transaction() as connection:
            connection.execute(
                "UPDATE canvas_transactions SET undone = ? WHERE canvas_id = ? "
                "AND sequence = ?",
                (1 if undone else 0, canvas_id, sequence),
            )

    def clear_canvas_redo(self, canvas_id: str) -> int:
        """A new edit clears the redo branch (R09)."""
        with self.transaction() as connection:
            cursor = connection.execute(
                "DELETE FROM canvas_transactions WHERE canvas_id = ? AND undone = 1",
                (canvas_id,),
            )
            return int(cursor.rowcount or 0)

    def trim_canvas_transactions(self, *, canvas_id: str, keep: int) -> int:
        """Keep the most recent ``keep`` saved edits; drop older history."""
        with self.transaction() as connection:
            cursor = connection.execute(
                "DELETE FROM canvas_transactions WHERE canvas_id = ? AND sequence "
                "NOT IN (SELECT sequence FROM canvas_transactions WHERE canvas_id = ? "
                "ORDER BY sequence DESC LIMIT ?)",
                (canvas_id, canvas_id, keep),
            )
            return int(cursor.rowcount or 0)

    # -- scheme snapshots and context selections -------------------------

    def insert_scheme_snapshot(
        self,
        *,
        snapshot_id: str,
        canvas_id: str,
        project_id: str,
        board_id: str,
        board_name: str,
        counter: int,
        content_hash: str,
        size: int,
        node_count: int,
        note: str,
        now: str,
    ) -> None:
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO scheme_snapshots (snapshot_id, canvas_id, project_id, "
                "board_id, board_name, counter, content_hash, bytes, node_count, "
                "note, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    snapshot_id,
                    canvas_id,
                    project_id,
                    board_id,
                    board_name,
                    counter,
                    content_hash,
                    size,
                    node_count,
                    note,
                    now,
                ),
            )

    def scheme_snapshot(self, snapshot_id: str) -> dict | None:
        with self.read() as connection:
            row = connection.execute(
                "SELECT * FROM scheme_snapshots WHERE snapshot_id = ?",
                (snapshot_id,),
            ).fetchone()
            return dict(row) if row is not None else None

    def canvas_scheme_snapshots(self, canvas_id: str) -> list[dict]:
        with self.read() as connection:
            rows = connection.execute(
                "SELECT * FROM scheme_snapshots WHERE canvas_id = ? "
                "ORDER BY created_at DESC, rowid DESC",
                (canvas_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def insert_context_selection(
        self,
        *,
        selection_id: str,
        project_id: str,
        canvas_id: str,
        board_id: str,
        canvas_counter: int,
        payload: dict,
        digest: str,
        now: str,
    ) -> None:
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO context_selections (selection_id, project_id, "
                "canvas_id, board_id, canvas_counter, state, payload_json, digest, "
                "confirmed_digest, confirmed_at, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, 'draft', ?, ?, NULL, NULL, ?, ?)",
                (
                    selection_id,
                    project_id,
                    canvas_id,
                    board_id,
                    canvas_counter,
                    _json(payload),
                    digest,
                    now,
                    now,
                ),
            )

    def update_context_selection(
        self,
        *,
        selection_id: str,
        canvas_counter: int,
        payload: dict,
        digest: str,
        state: str,
        now: str,
    ) -> None:
        """Replace the selection content; a confirmation only survives
        while the digest it was bound to is still the current one."""
        with self.transaction() as connection:
            connection.execute(
                "UPDATE context_selections SET canvas_counter = ?, payload_json = ?, "
                "digest = ?, state = ?, updated_at = ? WHERE selection_id = ?",
                (canvas_counter, _json(payload), digest, state, now, selection_id),
            )

    def confirm_context_selection(
        self, *, selection_id: str, digest: str, now: str
    ) -> None:
        with self.transaction() as connection:
            connection.execute(
                "UPDATE context_selections SET state = 'confirmed', "
                "confirmed_digest = ?, confirmed_at = ?, updated_at = ? "
                "WHERE selection_id = ?",
                (digest, now, now, selection_id),
            )

    def context_selection(self, selection_id: str) -> dict | None:
        with self.read() as connection:
            row = connection.execute(
                "SELECT * FROM context_selections WHERE selection_id = ?",
                (selection_id,),
            ).fetchone()
            return dict(row) if row is not None else None

    def canvas_context_selections(self, canvas_id: str) -> list[dict]:
        with self.read() as connection:
            rows = connection.execute(
                "SELECT * FROM context_selections WHERE canvas_id = ? "
                "ORDER BY updated_at DESC, rowid DESC",
                (canvas_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    # -- work requests and attempts --------------------------------------

    def insert_work_request(
        self,
        *,
        request_id: str,
        project_id: str,
        title: str,
        goal: str,
        target_stack: str,
        plan: dict,
        allowed_actions: list[str],
        result_schema: dict,
        context_selection_id: str,
        context_digest: str,
        binding_generation: int,
        state: str,
        expires_at: str | None,
        now: str,
    ) -> None:
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO work_requests (request_id, project_id, title, goal, "
                "target_stack, plan_json, allowed_actions_json, result_schema_json, "
                "context_selection_id, context_digest, binding_generation, state, "
                "capability_id, handoff_command, expires_at, counter, created_at, "
                "updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, "
                "?, 0, ?, ?)",
                (
                    request_id,
                    project_id,
                    title,
                    goal,
                    target_stack,
                    _json(plan),
                    _json(allowed_actions),
                    _json(result_schema),
                    context_selection_id,
                    context_digest,
                    binding_generation,
                    state,
                    expires_at,
                    now,
                    now,
                ),
            )

    def work_request(self, request_id: str) -> dict | None:
        with self.read() as connection:
            row = connection.execute(
                "SELECT * FROM work_requests WHERE request_id = ?", (request_id,)
            ).fetchone()
            return dict(row) if row is not None else None

    def project_work_requests(self, project_id: str) -> list[dict]:
        with self.read() as connection:
            rows = connection.execute(
                "SELECT * FROM work_requests WHERE project_id = ? "
                "ORDER BY updated_at DESC, rowid DESC",
                (project_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def set_work_request_state(
        self,
        *,
        request_id: str,
        state: str,
        capability_id: str | None = None,
        handoff_command: str | None = None,
        bump: int = 1,
        now: str,
    ) -> int:
        with self.transaction() as connection:
            if capability_id is None and handoff_command is None:
                connection.execute(
                    "UPDATE work_requests SET state = ?, counter = counter + ?, "
                    "updated_at = ? WHERE request_id = ?",
                    (state, bump, now, request_id),
                )
            else:
                connection.execute(
                    "UPDATE work_requests SET state = ?, capability_id = ?, "
                    "handoff_command = ?, counter = counter + ?, updated_at = ? "
                    "WHERE request_id = ?",
                    (state, capability_id, handoff_command, bump, now, request_id),
                )
            row = connection.execute(
                "SELECT counter FROM work_requests WHERE request_id = ?", (request_id,)
            ).fetchone()
            return int(row["counter"])

    def insert_work_attempt(
        self,
        *,
        attempt_id: str,
        request_id: str,
        sequence: int,
        state: str,
        capability_id: str | None,
        now: str,
    ) -> None:
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO work_attempts (attempt_id, request_id, sequence, state, "
                "lease_id, lease_expires_at, boot_id, capability_id, progress_json, "
                "result_json, result_digest, proposal_id, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, NULL, NULL, NULL, ?, '{}', NULL, NULL, NULL, ?, ?)",
                (attempt_id, request_id, sequence, state, capability_id, now, now),
            )

    def work_attempt(self, attempt_id: str) -> dict | None:
        with self.read() as connection:
            row = connection.execute(
                "SELECT * FROM work_attempts WHERE attempt_id = ?", (attempt_id,)
            ).fetchone()
            return dict(row) if row is not None else None

    def request_work_attempts(self, request_id: str) -> list[dict]:
        with self.read() as connection:
            rows = connection.execute(
                "SELECT * FROM work_attempts WHERE request_id = ? ORDER BY sequence ASC",
                (request_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def latest_work_attempt(self, request_id: str) -> dict | None:
        with self.read() as connection:
            row = connection.execute(
                "SELECT * FROM work_attempts WHERE request_id = ? "
                "ORDER BY sequence DESC LIMIT 1",
                (request_id,),
            ).fetchone()
            return dict(row) if row is not None else None

    def update_work_attempt(
        self,
        *,
        attempt_id: str,
        state: str,
        lease_id: str | None = None,
        lease_expires_at: str | None = None,
        boot_id: str | None = None,
        progress: dict | None = None,
        result: dict | None = None,
        result_digest: str | None = None,
        proposal_id: str | None = None,
        now: str,
    ) -> None:
        fields = ["state = ?", "updated_at = ?"]
        values: list[object] = [state, now]
        if lease_id is not None:
            fields.append("lease_id = ?")
            values.append(lease_id)
        if lease_expires_at is not None:
            fields.append("lease_expires_at = ?")
            values.append(lease_expires_at)
        if boot_id is not None:
            fields.append("boot_id = ?")
            values.append(boot_id)
        if progress is not None:
            fields.append("progress_json = ?")
            values.append(_json(progress))
        if result is not None:
            fields.append("result_json = ?")
            values.append(_json(result))
        if result_digest is not None:
            fields.append("result_digest = ?")
            values.append(result_digest)
        if proposal_id is not None:
            fields.append("proposal_id = ?")
            values.append(proposal_id)
        values.append(attempt_id)
        with self.transaction() as connection:
            connection.execute(
                f"UPDATE work_attempts SET {', '.join(fields)} WHERE attempt_id = ?",
                tuple(values),
            )

    # -- owner confirmations --------------------------------------------

    def insert_owner_confirmation(
        self,
        *,
        confirmation_id: str,
        project_id: str,
        run_id: str,
        object_type: str,
        object_id: str,
        source_hash: str,
        role: str,
        note: str,
        confirmed_by: str,
        now: str,
    ) -> None:
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO owner_confirmations (confirmation_id, project_id, "
                "run_id, object_type, object_id, source_hash, role, note, "
                "confirmed_by, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    confirmation_id,
                    project_id,
                    run_id,
                    object_type,
                    object_id,
                    source_hash,
                    role,
                    note,
                    confirmed_by,
                    now,
                ),
            )

    def owner_confirmation(self, confirmation_id: str) -> dict | None:
        with self.read() as connection:
            row = connection.execute(
                "SELECT * FROM owner_confirmations WHERE confirmation_id = ?",
                (confirmation_id,),
            ).fetchone()
            return dict(row) if row is not None else None

    def project_owner_confirmations(self, project_id: str) -> list[dict]:
        with self.read() as connection:
            rows = connection.execute(
                "SELECT * FROM owner_confirmations WHERE project_id = ? "
                "ORDER BY created_at DESC, rowid DESC",
                (project_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def find_owner_confirmation(
        self,
        *,
        project_id: str,
        run_id: str,
        object_type: str,
        object_id: str,
        source_hash: str,
        roles: tuple[str, ...],
    ) -> dict | None:
        """The confirmation that binds exactly this object hash and role."""
        placeholders = ",".join("?" for _ in roles)
        with self.read() as connection:
            row = connection.execute(
                "SELECT * FROM owner_confirmations WHERE project_id = ? AND "
                f"run_id = ? AND object_type = ? AND object_id = ? AND "
                f"source_hash = ? AND role IN ({placeholders}) "
                "ORDER BY created_at DESC LIMIT 1",
                (project_id, run_id, object_type, object_id, source_hash, *roles),
            ).fetchone()
            return dict(row) if row is not None else None

    # -- mutation ledger ------------------------------------------------

    def mutation(self, operation_id: str) -> dict | None:
        with self.read() as connection:
            row = connection.execute(
                "SELECT * FROM mutations WHERE operation_id = ?", (operation_id,)
            ).fetchone()
            return dict(row) if row is not None else None

    def record_mutation(
        self,
        *,
        operation_id: str,
        entity_kind: str,
        entity_id: str,
        payload_digest: str,
        resulting_counter: int | None,
        result_json: str,
        project_id: str | None,
        now: str,
    ) -> None:
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO mutations (operation_id, project_id, entity_kind, "
                "entity_id, payload_digest, resulting_counter, result_json, "
                "created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    operation_id,
                    project_id,
                    entity_kind,
                    entity_id,
                    payload_digest,
                    resulting_counter,
                    result_json,
                    now,
                ),
            )


def _utc_now() -> str:
    from datetime import datetime, timezone

    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    )


def _json(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, ensure_ascii=False)
