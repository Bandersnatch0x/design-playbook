#!/usr/bin/env python3
"""vNext integration smoke: packaged scripts import and core CLI exit codes."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
SCRIPTS = PACKAGE / "scripts"
PASS = Path(__file__).resolve().parent / "fixtures" / "pass"


class VNextIntegrationTests(unittest.TestCase):
    def test_packaged_scripts_import(self) -> None:
        for name in (
            "validate_run",
            "run_status",
            "contract_v1",
            "g7_contract_drift",
            "doctor",
            "_diagnostics",
        ):
            path = SCRIPTS / f"{name}.py"
            self.assertTrue(path.is_file(), path)

    def test_validate_run_json_and_doctor(self) -> None:
        spec = PASS / "zero-findings.spec.md"
        pb = PASS / "zero-findings.point-back.md"
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "validate_run.py"), str(spec), str(pb),
             "--format", "json"],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout), [])

        doctor = subprocess.run(
            [sys.executable, str(SCRIPTS / "doctor.py"), "--json"],
            capture_output=True, text=True, check=False,
        )
        self.assertIn(doctor.returncode, (0, 1), doctor.stdout + doctor.stderr)
        payload = json.loads(doctor.stdout)
        self.assertIn(payload["level"], ("ok", "degraded", "broken"))

    def test_contract_bind_and_g7_roundtrip(self) -> None:
        # One import seam (ADR-0022): package root on sys.path once, then
        # absolute design_playbook.* imports. No per-runtime path adapters.
        if str(PACKAGE) not in sys.path:
            sys.path.insert(0, str(PACKAGE))
        from design_playbook.scripts import contract_v1 as cv
        from design_playbook.scripts import g7_contract_drift as g7

        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            run = Path(tmp) / "run"
            cv.promote_fields(
                {
                    "a.goal": {
                        "value": "ship",
                        "provenance": "inferred",
                        "resolution": "assumed",
                    }
                },
                project_dir=project,
                changelog_summary="seed",
                at="2026-08-08T00:00:00Z",
            )
            bind = cv.bind_first(project, run, acknowledgements=["a.goal"])
            self.assertTrue(bind.ok)
            self.assertEqual(g7.check_g7(project, run), [])


if __name__ == "__main__":
    unittest.main()
