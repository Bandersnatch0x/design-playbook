#!/usr/bin/env python3
"""Contract tests for the stage registry module (ADR-0021).

Covers the packaged ``stages.py`` surface: the ``STAGES`` table (the SKILL.md
step mirror for status/resume narration) and the shared artifact-name
constants consumed by run_status.py and validate_run.py. The registry is data
only — no behavior, no run-state SSOT.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "packages" / "design-playbook"

# One import seam (ADR-0022): package root on sys.path once, then absolute
# design_playbook.* imports below. No per-runtime sys.path adapters.
if str(PKG) not in sys.path:
    sys.path.insert(0, str(PKG))

from design_playbook.scripts.stages import (  # noqa: E402
    DECISION_REPORT,
    EVIDENCE_MANIFEST,
    EVIDENCE_PREFIX,
    POINT_BACK,
    SPEC_MD,
    STAGES,
)


def _markers(key: str) -> tuple[str, ...]:
    for stage_key, _skill, markers in STAGES:
        if stage_key == key:
            return markers
    return ()


class StagesRegistryTests(unittest.TestCase):
    def test_preview_presence_is_derived_by_preview_integrity(self) -> None:
        self.assertEqual(_markers("preview"), ())

    def test_evidence_stage_declares_manifest(self) -> None:
        self.assertIn(EVIDENCE_MANIFEST, _markers("evidence"))

    def test_stage_order_matches_pipeline(self) -> None:
        keys = [key for key, _skill, _markers in STAGES]
        self.assertEqual(keys, [
            "baseline", "reference", "spec", "plan", "decision",
            "preview", "fill", "craft", "evidence", "accept",
        ])

    def test_markers_use_shared_constants(self) -> None:
        # The table and the constants cannot disagree: overlapping markers
        # must be the exact shared constants.
        self.assertEqual(_markers("spec"), (SPEC_MD,))
        self.assertEqual(_markers("decision"), (DECISION_REPORT,))
        self.assertEqual(_markers("evidence"), (EVIDENCE_MANIFEST,))
        self.assertEqual(_markers("accept"), (POINT_BACK,))

    def test_shared_constants_are_stable_names(self) -> None:
        self.assertEqual(EVIDENCE_PREFIX, "evidence/")
        self.assertEqual(EVIDENCE_MANIFEST, "evidence/manifest.jsonl")
        self.assertEqual(POINT_BACK, "point-back.md")
        self.assertEqual(DECISION_REPORT, "decision-report.md")
        self.assertEqual(SPEC_MD, "spec.md")
        # Prefix relationship: the manifest lives under evidence/.
        self.assertTrue(EVIDENCE_MANIFEST.startswith(EVIDENCE_PREFIX))


if __name__ == "__main__":
    unittest.main()
