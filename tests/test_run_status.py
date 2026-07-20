#!/usr/bin/env python3
"""Black-box tests for scripts/run_status.py."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN_STATUS = ROOT / "scripts" / "run_status.py"


def _run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(RUN_STATUS), *args],
        cwd=cwd or ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


class RunStatusTests(unittest.TestCase):
    def test_status_from_spec_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run-a"
            run_root.mkdir()
            (run_root / "spec.md").write_text("# L1\n", encoding="utf-8")
            result = _run(str(run_root), "--json")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertTrue(payload["stages"][0]["present"])
            self.assertIn("Resume", payload["next"])

    def test_status_after_accept_pass(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "run-b"
            run_root.mkdir()
            (run_root / "spec.md").write_text("spec\n", encoding="utf-8")
            (run_root / "point-back.md").write_text(
                "## Verdict\n\nPass\n", encoding="utf-8"
            )
            result = _run(str(run_root), "--json")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["verdict"], "Pass")
            self.assertIn("complete", payload["next"].lower())


if __name__ == "__main__":
    unittest.main()
