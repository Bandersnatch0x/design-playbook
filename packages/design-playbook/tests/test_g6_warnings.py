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


if __name__ == "__main__":
    unittest.main()
