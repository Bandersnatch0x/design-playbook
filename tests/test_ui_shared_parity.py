#!/usr/bin/env python3
"""ADR-0048: the workbench's shared-UI copies match their canonical files.

``packages/design-playbook/mcp/_shared/`` holds the only editable copy of
the shared UI layer. The workbench ships flat byte copies beside a sha256
lock written by ``scripts/sync_ui_shared.py``. This test asserts canonical
== copy == lock, so an edit to either side that skipped the sync script
fails here instead of shipping drifted bytes.
"""
from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import sync_ui_shared  # noqa: E402

LOCK = sync_ui_shared.TARGET_DIR / sync_ui_shared.LOCK_NAME


class UiSharedParityTest(unittest.TestCase):
    def _lock(self) -> dict:
        return json.loads(LOCK.read_text(encoding="utf-8"))

    def test_lock_covers_exactly_the_declared_copies(self) -> None:
        lock = self._lock()
        self.assertEqual(lock["schemaVersion"], 1)
        self.assertEqual(sorted(lock["files"]), sorted(sync_ui_shared.COPIES))

    def test_every_copy_matches_its_canonical_file_and_the_lock(self) -> None:
        for name, digest in self._lock()["files"].items():
            with self.subTest(name=name):
                canonical = sync_ui_shared.CANONICAL_DIR / name
                copy = sync_ui_shared.TARGET_DIR / name
                self.assertTrue(canonical.is_file(), canonical)
                self.assertTrue(copy.is_file(), copy)
                self.assertEqual(
                    hashlib.sha256(canonical.read_bytes()).hexdigest(), digest
                )
                self.assertEqual(hashlib.sha256(copy.read_bytes()).hexdigest(), digest)

    def test_no_unlocked_copy_of_a_canonical_file_ships(self) -> None:
        # A file copied by hand — not through the sync script — must not
        # ride along unlocked; a canonical file with no copy is fine.
        locked = set(self._lock()["files"])
        for canonical in sorted(sync_ui_shared.CANONICAL_DIR.iterdir()):
            if not canonical.is_file():
                continue
            copy = sync_ui_shared.TARGET_DIR / canonical.name
            with self.subTest(name=canonical.name):
                if copy.is_file():
                    self.assertIn(canonical.name, locked)


if __name__ == "__main__":
    unittest.main()
