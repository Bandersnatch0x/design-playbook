"""Shared Preview transaction error vocabulary.

One definition per class, imported by the lock and record modules and by the
transaction that raises them, so `except` semantics are unchanged by the split.
"""
from __future__ import annotations

class PreviewTransactionError(ValueError):
    """Recoverable transaction failure with actionable artifact context."""

    def __init__(
        self, message: str, *, retryable: bool, round_n: int,
        decision_id: str, artifact: str,
    ) -> None:
        super().__init__(message)
        self.details = {
            "error": "preview_transaction",
            "message": message,
            "retryable": retryable,
            "round": round_n,
            "decision_id": decision_id,
            "artifact": artifact,
        }

class TransactionConflict(PreviewTransactionError):
    """Existing same-round authority cannot be replaced by this request."""

class ConfirmRecordError(ValueError):
    """A durable confirm artifact does not match its decision authority."""

class DirectoryLockError(OSError):
    """A shared Preview-directory lease could not be acquired or maintained."""
