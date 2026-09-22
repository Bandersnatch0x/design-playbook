#!/usr/bin/env python3
"""D-2 regression tests: shaping_log CLI --mapping-json (2026-09-22 rerun)."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[1] / "scripts" / "shaping_log.py"
)


class ShapingLogCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.log = Path(self._tmp.name) / "shaping-log.jsonl"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _append(self, *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "append", str(self.log), *extra],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )

    def _events(self) -> list[dict]:
        return [
            json.loads(line)
            for line in self.log.read_text(encoding="utf-8").splitlines()
        ]

    def test_mapping_json_writes_real_list(self) -> None:
        proc = self._append(
            "--type", "projected",
            "--mapping-json",
            '[{"decision":"D-1","field":"l2.x","spec_section":"L2"}]',
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        event = self._events()[0]
        self.assertIsInstance(event["mappings"], list)
        self.assertEqual(event["mappings"][0]["decision"], "D-1")

    def test_mapping_json_rejects_bad_shape(self) -> None:
        for bad in ('{"a":1}', '[{"decision":"D-1"}]', "not-json"):
            proc = self._append("--type", "projected", "--mapping-json", bad)
            self.assertEqual(proc.returncode, 1, bad)
            self.assertIn("--mapping-json", proc.stdout + proc.stderr)

    def test_plain_key_value_stays_string(self) -> None:
        proc = self._append("--type", "asked", "--question", "Q1")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        event = self._events()[0]
        self.assertEqual(event["question"], "Q1")
        self.assertNotIn("mappings", event)


if __name__ == "__main__":
    unittest.main()
