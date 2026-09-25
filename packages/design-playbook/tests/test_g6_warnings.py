#!/usr/bin/env python3
"""D-4 regression tests: G6 batch-ts WARN only on real ambiguity."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
if str(PACKAGE) not in sys.path:
    sys.path.insert(0, str(PACKAGE))

from design_playbook.scripts.g6_warnings import (  # noqa: E402
    check_manifest_ts_warnings,
    check_superseded_ledger_warnings,
)

TS = "2026-09-22T22:40:58+08:00"


def _entry(criterion: str, artifact: str, ts: str = TS) -> dict:
    return {"criterion": criterion, "artifact": artifact, "ts": ts}


class BatchTsWarningTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.evidence_dir = Path(self._tmp.name) / "evidence"
        self.evidence_dir.mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _check(self, entries: list[dict]):
        return check_manifest_ts_warnings(self.evidence_dir, entries=entries)

    def test_shared_ts_one_row_per_criterion_stays_quiet(self) -> None:
        entries = [_entry("L6.1", "a.png"), _entry("L6.2", "b.png")]
        self.assertEqual(self._check(entries), [])

    def test_shared_ts_multiple_rows_one_criterion_warns(self) -> None:
        entries = [_entry("L6.1", "a.png"), _entry("L6.1", "b.png")]
        warns = self._check(entries)
        self.assertEqual(len(warns), 1)
        self.assertEqual(warns[0].severity, "warning")

    def test_distinct_ts_never_warns(self) -> None:
        entries = [
            _entry("L6.1", "a.png"),
            _entry("L6.1", "b.png", ts="2026-09-22T22:41:00+08:00"),
        ]
        self.assertEqual(self._check(entries), [])


class SupersededArtifactWarningTests(unittest.TestCase):
    """P2-3: the latest binding is the latest instant, not the largest string."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.evidence_dir = Path(self._tmp.name) / "evidence"
        self.evidence_dir.mkdir()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _check(self, entries: list[dict]):
        return check_superseded_ledger_warnings(
            "",
            self.evidence_dir,
            observed_rows=[("L6.1", "evidence/a.png")],
            entries=entries,
        )

    def test_mixed_offset_stamps_order_by_instant(self) -> None:
        warns = self._check([
            _entry("L6.1", "a.png", ts="2026-09-24T12:00:00+08:00"),
            _entry("L6.1", "b.png", ts="2026-09-24T10:00:00Z"),
        ])
        self.assertEqual([warn.rule_id for warn in warns], ["G6.superseded_artifact"])

    def test_unusable_ts_stays_quiet(self) -> None:
        warns = self._check([
            _entry("L6.1", "a.png", ts="2026-09-24T12:00:00+08:00"),
            _entry("L6.1", "b.png", ts="2026-09-24 10:00"),
        ])
        self.assertEqual(warns, [])


if __name__ == "__main__":
    unittest.main()
