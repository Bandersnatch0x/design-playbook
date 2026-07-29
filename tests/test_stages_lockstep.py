#!/usr/bin/env python3
"""Lockstep test: run_status.STAGES artifact markers agree with validate_run regexes.

The STAGES tuple (scripts/run_status.py) hand-mirrors the Design I/O
pipeline artifact filenames; validate_run.py encodes the same names as
regex constants (CONFIRM_JSON / ROUND_HTML / DECISION_JSON) and
_preview_integrity re-derives round numbers. A comment in run_status.py
warns to "sync this table" when SKILL.md changes — this test turns that
comment into a failing test for the cheapest-to-break invariant: the
preview/evidence artifact names the two modules rely on must agree.

See architecture candidate 5 (contract SSOT). Full unification is deferred
to ADR-0010 P1; this catches silent drift until then.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_VALIDATE_RUN_DIR = ROOT / "packages" / "design-playbook" / "scripts"
if str(_VALIDATE_RUN_DIR) not in sys.path:
    sys.path.insert(0, str(_VALIDATE_RUN_DIR))

sys.path.insert(0, str(ROOT / "scripts"))

from run_status import STAGES  # noqa: E402
from validate_run import CONFIRM_JSON, ROUND_HTML  # noqa: E402


def _markers(key: str) -> tuple[str, ...]:
    for k, _skill, markers in STAGES:
        if k == key:
            return markers
    return ()


class StagesLockstepTests(unittest.TestCase):
    def test_confirm_marker_matches_regex(self) -> None:
        """The confirm-round-N.json name STAGES uses must be accepted by CONFIRM_JSON."""
        markers = _markers("preview")
        confirm_markers = [Path(m).name for m in markers if "confirm" in m]
        self.assertTrue(confirm_markers, "no confirm-round marker in STAGES")
        for leaf in confirm_markers:
            # STAGES uses a round-1 literal; CONFIRM_JSON must accept any N.
            self.assertIsNotNone(
                CONFIRM_JSON.match(leaf),
                f"CONFIRM_JSON rejects STAGES confirm marker {leaf!r}",
            )

    def test_round_marker_matches_regex(self) -> None:
        """Any round-N.html name STAGES uses must be accepted by ROUND_HTML."""
        markers = _markers("preview")
        round_markers = [Path(m).name for m in markers if "round" in m and m.endswith(".html")]
        for leaf in round_markers:
            self.assertIsNotNone(
                ROUND_HTML.match(leaf),
                f"ROUND_HTML rejects STAGES round marker {leaf!r}",
            )

    def test_evidence_marker_present(self) -> None:
        """The evidence stage must declare the manifest.jsonl artifact validate_run reads."""
        markers = _markers("evidence")
        self.assertTrue(
            any(m == "evidence/manifest.jsonl" for m in markers),
            f"evidence stage missing evidence/manifest.jsonl: {markers}",
        )


if __name__ == "__main__":
    unittest.main()
