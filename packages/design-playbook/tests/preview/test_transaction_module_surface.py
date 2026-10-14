#!/usr/bin/env python3
"""Frozen import surface for transaction.py after the T-111 module split.

Every top-level name `transaction.py` defined at dccdf3f must still be a module
attribute here, and the moved definitions must be the very same objects the new
owner modules expose. This is what makes the split an equivalence replacement:
drop one re-export and this file fails.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

# One import seam (ADR-0022): package root on sys.path once, then absolute
# design_playbook.* imports below. No per-runtime sys.path adapters.
_PKG_ROOT = Path(__file__).resolve().parents[2]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))
from design_playbook.mcp.preview import entry_io  # noqa: E402
from design_playbook.mcp.preview import locking  # noqa: E402
from design_playbook.mcp.preview import transaction  # noqa: E402
from design_playbook.mcp.preview import transaction_errors  # noqa: E402

# AST top-level defs/classes/constants of transaction.py at dccdf3f, sorted.
FROZEN_NAMES = (
    "BrowserCollector",
    "ConfirmRecordError",
    "DIRECTORY_LOCK_HEARTBEAT_SECONDS",
    "DIRECTORY_LOCK_POLL_SECONDS",
    "DIRECTORY_LOCK_STALE_SECONDS",
    "DIRECTORY_LOCK_TIMEOUT_SECONDS",
    "DirectoryLockError",
    "ENTRY_SCHEMA_VERSION",
    "LOCK_HEARTBEAT_SECONDS",
    "LOCK_STALE_SECONDS",
    "PROJECTION_LOCK_NAME",
    "PreviewTransactionError",
    "TransactionConflict",
    "_REPLACE_RETRY_ATTEMPTS",
    "_REPLACE_RETRY_SECONDS",
    "_claim_stale_lock",
    "_commit_projections",
    "_commit_projections_unlocked",
    "_confirm_record",
    "_directory_lock_is_stale",
    "_floor_verdict",
    "_ledger_record",
    "_lock_metadata",
    "_lock_owner",
    "_release_lock_guard",
    "_result",
    "_round_from_path",
    "_round_lock",
    "_run_locked",
    "_try_acquire_directory_lease",
    "_try_lock_guard",
    "atomic_write",
    "directory_lock",
    "json_text",
    "load_confirm_for_entry",
    "load_entry",
    "render_log",
    "run_preview_transaction",
    "valid_entries",
)

# name -> module that owns the definition after the split.
OWNERS = {
    "PreviewTransactionError": transaction_errors,
    "TransactionConflict": transaction_errors,
    "ConfirmRecordError": transaction_errors,
    "DirectoryLockError": transaction_errors,
    "ENTRY_SCHEMA_VERSION": entry_io,
    "_REPLACE_RETRY_ATTEMPTS": entry_io,
    "_REPLACE_RETRY_SECONDS": entry_io,
    "atomic_write": entry_io,
    "json_text": entry_io,
    "load_entry": entry_io,
    "_round_from_path": entry_io,
    "_confirm_record": entry_io,
    "load_confirm_for_entry": entry_io,
    "render_log": entry_io,
    "valid_entries": entry_io,
    "_ledger_record": entry_io,
    "LOCK_HEARTBEAT_SECONDS": locking,
    "LOCK_STALE_SECONDS": locking,
    "DIRECTORY_LOCK_TIMEOUT_SECONDS": locking,
    "DIRECTORY_LOCK_STALE_SECONDS": locking,
    "DIRECTORY_LOCK_HEARTBEAT_SECONDS": locking,
    "DIRECTORY_LOCK_POLL_SECONDS": locking,
    "PROJECTION_LOCK_NAME": locking,
    "_lock_metadata": locking,
    "_claim_stale_lock": locking,
    "_lock_owner": locking,
    "_try_lock_guard": locking,
    "_release_lock_guard": locking,
    "_directory_lock_is_stale": locking,
    "_try_acquire_directory_lease": locking,
    "directory_lock": locking,
    "_round_lock": locking,
}


class TransactionModuleSurfaceTests(unittest.TestCase):
    def test_frozen_names_are_still_module_attributes(self) -> None:
        missing = [name for name in FROZEN_NAMES if not hasattr(transaction, name)]
        self.assertEqual(missing, [], f"transaction.py lost a re-export: {missing}")

    def test_moved_names_are_the_owner_objects(self) -> None:
        for name, owner in OWNERS.items():
            self.assertIs(
                getattr(transaction, name), getattr(owner, name),
                msg=f"{name} is not the object owned by {owner.__name__}")

    def test_orchestration_stays_in_transaction(self) -> None:
        # The commit/result/entrypoint bodies must not move; they call the
        # compatibility owner and the re-exported primitives.
        for name in ("run_preview_transaction", "_commit_projections",
                     "_commit_projections_unlocked", "_result", "_run_locked",
                     "_floor_verdict", "BrowserCollector"):
            self.assertEqual(
                getattr(transaction, name).__module__,
                transaction.__name__, msg=f"{name} left the orchestrator")

    def test_error_classes_have_one_definition(self) -> None:
        # Single identity keeps `except` semantics across the split: a conflict
        # raised through the owner module is catchable through transaction's
        # class, and the subclass chain is intact.
        self.assertIs(
            transaction_errors.TransactionConflict,
            transaction.TransactionConflict)
        self.assertIs(
            transaction.TransactionConflict.__bases__[0],
            transaction.PreviewTransactionError)
        raised = transaction_errors.TransactionConflict(
            "identity probe", retryable=False, round_n=1,
            decision_id="d", artifact="a",
        )
        with self.assertRaises(transaction.PreviewTransactionError):
            raise raised

    def test_moved_modules_do_not_import_back(self) -> None:
        # No cycle: the leaf modules must not name the orchestrator.
        for module in (transaction_errors, entry_io, locking):
            source = Path(module.__file__).read_text(encoding="utf-8")
            self.assertNotIn(
                "preview import transaction", source,
                msg=f"{module.__name__} imports the transaction orchestrator")
            self.assertNotIn(
                "preview.transaction import", source,
                msg=f"{module.__name__} imports from the transaction module")


if __name__ == "__main__":
    unittest.main()
