#!/usr/bin/env python3
"""Contract tests for non-Preview run-status stage markers."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_status import STAGES  # noqa: E402


def _markers(key: str) -> tuple[str, ...]:
    for stage_key, _skill, markers in STAGES:
        if stage_key == key:
            return markers
    return ()


class StagesRegistryTests(unittest.TestCase):
    def test_preview_presence_is_derived_by_preview_integrity(self) -> None:
        self.assertEqual(_markers("preview"), ())

    def test_evidence_stage_declares_manifest(self) -> None:
        self.assertIn("evidence/manifest.jsonl", _markers("evidence"))


if __name__ == "__main__":
    unittest.main()
