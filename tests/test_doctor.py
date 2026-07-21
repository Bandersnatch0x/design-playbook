#!/usr/bin/env python3
"""Smoke tests for scripts/doctor.py."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCTOR = ROOT / "scripts" / "doctor.py"


def _load_doctor_module():
    """Import scripts/doctor.py as an in-process module.

    doctor.py computes ``ROOT`` from ``__file__`` (not cwd), so the
    subprocess + tmp-fixture pattern used by tests/test_release.py cannot
    redirect its path resolution. Loading in-process lets the drift test
    point ``ROOT`` / ``PKG`` at a tmp fixture and call ``check_codex_manifest``
    directly.
    """
    spec = importlib.util.spec_from_file_location("dpb_doctor_under_test", DOCTOR)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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
        # Issue 07: doctor must surface the Codex dual-publish manifest
        # (ADR-0009) so drift between Claude and Codex surfaces is visible
        # in the read-only diagnostic, mirroring validate.py.
        self.assertIn("Codex manifest", result.stdout)
        self.assertIn(".codex-plugin/plugin.json version matches", result.stdout)
        self.assertIn(".agents marketplace plugins[0].source.path exists", result.stdout)

    def test_check_codex_manifest_fails_on_version_drift(self) -> None:
        """Issue 07 / H5: ``check_codex_manifest`` must surface Claude vs
        Codex ``plugin.json`` version drift as a FAIL, not silently OK it.
        Without this guard, doctor could regress to always-OK while CI
        stays green and the Codex marketplace ships a stale version
        (mirrors ``tests/test_release.py::
        test_codex_plugin_json_version_must_match_claude`` for the
        read-only diagnostic surface).
        """
        doctor = _load_doctor_module()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            pkg = tmp_root / "packages" / "design-playbook"
            (pkg / ".claude-plugin").mkdir(parents=True)
            (pkg / ".codex-plugin").mkdir(parents=True)
            (pkg / ".claude-plugin" / "plugin.json").write_text(
                json.dumps({"name": "design-playbook", "version": "0.4.4"}),
                encoding="utf-8",
            )
            # Codex side drifted to 9.9.9 (the bug: bump漏改 .codex-plugin).
            (pkg / ".codex-plugin" / "plugin.json").write_text(
                json.dumps({"name": "design-playbook", "version": "9.9.9"}),
                encoding="utf-8",
            )

            orig_root = doctor.ROOT
            orig_pkg = doctor.PKG
            orig_failures = doctor.failures[:]
            doctor.ROOT = tmp_root
            doctor.PKG = pkg
            doctor.failures = []
            try:
                doctor.check_codex_manifest()
                captured = list(doctor.failures)
            finally:
                doctor.ROOT = orig_root
                doctor.PKG = orig_pkg
                doctor.failures = orig_failures

        drift_hits = [
            f for f in captured
            if "drift" in f.lower() and "9.9.9" in f and "0.4.4" in f
        ]
        self.assertTrue(
            drift_hits,
            f"expected codex version drift failure, got: {captured}",
        )


if __name__ == "__main__":
    unittest.main()
