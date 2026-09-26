#!/usr/bin/env python3
"""P2-3 regression: latest-binding selection compares ts instants, not strings."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
if str(PACKAGE) not in sys.path:
    sys.path.insert(0, str(PACKAGE))

from design_playbook.scripts.g6_evidence import select_bound_entry  # noqa: E402

# 10:00Z is the later capture; its string sorts below the older +08:00 stamp.
LATER = "2026-09-24T10:00:00Z"
EARLIER = "2026-09-24T12:00:00+08:00"
SAME_INSTANT = "2026-09-24T18:00:00+08:00"


def _entry(ts: object, digest: str = "d") -> dict:
    return {"criterion": "L6.1", "artifact": "a.png", "ts": ts, "sha256": digest}


class LatestBindingInstantTests(unittest.TestCase):
    def test_mixed_offsets_pick_the_later_instant(self) -> None:
        entries = [_entry(EARLIER, "older"), _entry(LATER, "newer")]
        self.assertEqual(
            select_bound_entry(entries, "L6.1", "a.png")["sha256"], "newer")

    def test_unknown_pair_has_no_binding(self) -> None:
        self.assertIsNone(select_bound_entry([_entry(LATER)], "L6.2", "a.png"))

    def test_two_entries_at_one_instant_stay_ambiguous(self) -> None:
        entries = [_entry(LATER, "first"), _entry(SAME_INSTANT, "tie")]
        with self.assertRaises(ValueError) as caught:
            select_bound_entry(entries, "L6.1", "a.png")
        self.assertEqual(str(caught.exception), "conflicting-bindings")

    def test_repeated_identical_entry_is_not_a_conflict(self) -> None:
        entry = _entry(LATER)
        self.assertEqual(select_bound_entry([entry, dict(entry)], "L6.1", "a.png"), entry)

    def test_unusable_timestamps_fail_closed(self) -> None:
        for ts in ("2026-09-24T23:00:00", "2026-09-24 10:00", "", None, 1_758_000_000):
            with self.subTest(ts=ts):
                with self.assertRaises(ValueError) as caught:
                    select_bound_entry([_entry(EARLIER), _entry(ts)], "L6.1", "a.png")
                self.assertEqual(str(caught.exception), "invalid-binding-timestamp")


if __name__ == "__main__":
    unittest.main()
