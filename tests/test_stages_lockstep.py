#!/usr/bin/env python3
"""Lockstep test: run_status.STAGES preview/evidence markers agree with validate_run regexes.

The STAGES tuple (scripts/run_status.py) hand-mirrors the Design I/O
pipeline artifact filenames; validate_run.py encodes the confirm/round
names as regex constants (CONFIRM_JSON / ROUND_HTML). A comment in
run_status.py warns to "sync this table" when SKILL.md changes — this
test turns that comment into a failing test for the cheapest-to-break
invariant: the confirm/round artifact names the two modules rely on must
agree.

DECISION_JSON is not locked here: decision-round-N.json is a durable-gate
internal artifact, not a STAGES marker, so there is no STAGES-side name
to lock against. Full unification is deferred to ADR-0010 P1; this
catches silent drift on the confirm/round scheme until then.
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
        """The round-N.html sibling of STAGES' confirm marker must be accepted by ROUND_HTML.

        STAGES does not enumerate round-N.html directly (only preview/log.md
        and confirm-round-N.json), so derive the sibling of the confirm marker
        — the same round-N.html the preview actually serves — and assert
        ROUND_HTML accepts it. Without this derivation the loop would be empty
        and the test would pass trivially (reviewer: vacuous-assertion HIGH).
        """
        markers = _markers("preview")
        confirm = next(
            (Path(m).name for m in markers
             if m.endswith(".json") and "confirm" in m),
            None,
        )
        self.assertIsNotNone(
            confirm, "no confirm marker to derive the round html sibling from")
        sibling = confirm.replace("confirm-", "").replace(".json", ".html")
        self.assertIsNotNone(
            ROUND_HTML.match(sibling),
            f"ROUND_HTML rejects derived round marker {sibling!r}",
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
