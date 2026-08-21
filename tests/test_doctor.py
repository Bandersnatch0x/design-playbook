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
PACKAGE_DOCTOR = ROOT / "packages" / "design-playbook" / "scripts" / "doctor.py"
sys.path.insert(0, str(ROOT / "scripts"))
from _checks import expected_commands  # noqa: E402


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
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("DOCTOR PASSED", result.stdout)
        self.assertIn(".mcp.json", result.stdout)
        self.assertIn("mcp/preview/server.py", result.stdout)
        self.assertIn("gate 1 structural smoke", result.stdout)
        self.assertIn("8 skills present", result.stdout)
        # Issue #71: the audit-preferences module is part of the shipped
        # scripts surface; doctor's layout check must fail closed on it.
        self.assertIn("scripts/audit_preferences.py", result.stdout)
        self.assertIn("npm release group", result.stdout)
        # Lockstep with COMMAND_INVENTORY / plugin version (was hardcoded 4 pre-0.12).
        plugin = json.loads(
            (ROOT / "packages/design-playbook/.claude-plugin/plugin.json")
            .read_text(encoding="utf-8")
        )
        cmds = expected_commands(str(plugin.get("version", "")))
        self.assertIsNotNone(cmds)
        self.assertIn(f"{len(cmds)} commands present", result.stdout)
        # Issue 07: doctor must surface the Codex dual-publish manifest
        # (ADR-0009) so drift between Claude and Codex surfaces is visible
        # in the read-only diagnostic, mirroring validate.py.
        self.assertIn("Codex manifest", result.stdout)
        self.assertIn(".codex-plugin/plugin.json version matches", result.stdout)
        self.assertIn(".agents marketplace plugins[0].source.path exists", result.stdout)
        # Issue 64: doctor must emit the declarative host-vision reminder
        # (self-declared capability + text-only fallback path) without any
        # auto-detection.
        self.assertIn("host vision capability (self-declared)", result.stdout)
        self.assertIn("doctor does not auto-detect it", result.stdout)
        self.assertIn("reference-intake falls back to", result.stdout)

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

    def test_check_host_vision_is_advisory_only(self) -> None:
        """Issue 64: ``check_host_vision`` is a fixed info-level reminder.
        It must emit the self-declaration + fallback wording and must not
        record any failure or warning, so it cannot influence the doctor
        verdict or exit code. It also performs no detection: the function
        reads no files, calls no model, and takes no arguments.
        """
        doctor = _load_doctor_module()
        orig_failures = doctor.failures[:]
        orig_warnings = doctor.warnings[:]
        doctor.failures = []
        doctor.warnings = []
        try:
            doctor.check_host_vision()
            captured_failures = list(doctor.failures)
            captured_warnings = list(doctor.warnings)
        finally:
            doctor.failures = orig_failures
            doctor.warnings = orig_warnings

        self.assertEqual(captured_failures, [])
        self.assertEqual(captured_warnings, [])

    def test_check_release_group_fails_on_dependency_drift(self) -> None:
        doctor = _load_doctor_module()
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            pkg = tmp_root / "packages" / "design-playbook"
            dsh_pkg = tmp_root / "packages" / "dsh-design-playbook"
            pkg.mkdir(parents=True)
            dsh_pkg.mkdir(parents=True)
            (pkg / "package.json").write_text(
                json.dumps({"name": "design-playbook", "version": "1.2.3"}),
                encoding="utf-8",
            )
            (dsh_pkg / "package.json").write_text(
                json.dumps(
                    {
                        "name": "dsh-design-playbook",
                        "version": "1.2.3",
                        "dependencies": {"design-playbook": "^1.1.0"},
                    }
                ),
                encoding="utf-8",
            )

            orig_root = doctor.ROOT
            orig_pkg = doctor.PKG
            orig_failures = doctor.failures[:]
            doctor.ROOT = tmp_root
            doctor.PKG = pkg
            doctor.failures = []
            try:
                doctor.check_release_group()
                captured = list(doctor.failures)
            finally:
                doctor.ROOT = orig_root
                doctor.PKG = orig_pkg
                doctor.failures = orig_failures

        self.assertIn(
            "dsh-design-playbook dependency on design-playbook '^1.1.0'; "
            "expected '^1.2.3'",
            captured,
        )


    def test_check_codex_mcp_targets_fails_on_missing_target(self) -> None:
        """H3: ``_check_codex_mcp_targets`` must FAIL when a Codex MCP
        server's ``args[0]`` target does not resolve on disk. The split
        helper takes a crafted payload directly, so this exercises the
        fail branch without the four-file fixture the orchestrator reads.
        """
        doctor = _load_doctor_module()
        payload = {
            "mcpServers": {
                "design-playbook-preview": {"args": ["./does-not-exist/preview.py"]},
                "design-playbook-evidence": {"args": ["./does-not-exist/evidence.py"]},
            }
        }
        orig_failures = doctor.failures[:]
        doctor.failures = []
        try:
            doctor._check_codex_mcp_targets(payload)
            captured = list(doctor.failures)
        finally:
            doctor.failures = orig_failures

        target_fails = [
            f for f in captured
            if "target missing" in f and "./does-not-exist/preview.py" in f
        ]
        self.assertTrue(
            target_fails,
            f"expected missing-target failure, got: {captured}",
        )

    def test_check_agents_marketplace_fails_on_missing_source_path(self) -> None:
        """H3: ``_check_agents_marketplace`` must FAIL when
        ``plugins[0].source.path`` points at a directory that does not
        exist on disk. Mirrors the kind of regression a repo move would
        cause; the helper is called directly with a crafted payload.
        """
        doctor = _load_doctor_module()
        payload = {"plugins": [{"source": {"path": "./does-not-exist-pkg"}}]}
        orig_failures = doctor.failures[:]
        doctor.failures = []
        try:
            doctor._check_agents_marketplace(payload)
            captured = list(doctor.failures)
        finally:
            doctor.failures = orig_failures

        source_fails = [
            f for f in captured
            if "missing on disk" in f and "./does-not-exist-pkg" in f
        ]
        self.assertTrue(
            source_fails,
            f"expected missing source-path failure, got: {captured}",
        )


class PackagedDoctorAuditPreferencesTests(unittest.TestCase):
    def _run(self, repo: Path) -> dict:
        result = subprocess.run(
            [sys.executable, str(PACKAGE_DOCTOR), "--json", "--repo-root", str(repo)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        self.assertIn(result.returncode, (0, 1), result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_projects_effective_preference_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            prefs = repo / ".design-playbook" / "preferences.yaml"
            prefs.parent.mkdir()
            prefs.write_text(
                "craft_guard: false\nobserve: true\nasked: true\n",
                encoding="utf-8",
            )
            payload = self._run(repo)
        check = next(
            item for item in payload["checks"]
            if item["name"] == "audit_preferences.state")
        self.assertTrue(check["ok"])
        self.assertTrue(check["detail"]["asked"])
        self.assertFalse(check["detail"]["stages"]["craft_guard"]["runs"])
        self.assertEqual(check["detail"]["stages"]["craft_guard"]["source"], "repo")

    def test_corrupt_preference_layer_degrades(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            prefs = repo / ".design-playbook" / "preferences.yaml"
            prefs.parent.mkdir()
            prefs.write_text("observe: [broken\n", encoding="utf-8")
            payload = self._run(repo)
        check = next(
            item for item in payload["checks"]
            if item["name"] == "audit_preferences.state")
        self.assertFalse(check["ok"])
        self.assertEqual(check["level"], "degraded")
        self.assertEqual(check["detail"]["invalid_files"], ["repo"])


if __name__ == "__main__":
    unittest.main()
