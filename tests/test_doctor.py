#!/usr/bin/env python3
"""Smoke tests for scripts/doctor.py."""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCTOR = ROOT / "scripts" / "doctor.py"


class DoctorTests(unittest.TestCase):
    def test_doctor_passes_on_repo(self) -> None:
        result = subprocess.run(
            [sys.executable, str(DOCTOR), "--skip-self-check"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("DOCTOR PASSED", result.stdout)
        self.assertIn(".mcp.json", result.stdout)
        self.assertIn("mcp/preview/server.py", result.stdout)
        self.assertIn("gate 1 structural smoke", result.stdout)
        self.assertIn("6 skills present", result.stdout)
        self.assertIn("3 commands present", result.stdout)


if __name__ == "__main__":
    unittest.main()
