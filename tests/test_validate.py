#!/usr/bin/env python3
"""Black-box regression tests for the static validation gate.

Mirrors ``tests/test_release.py``: each test builds an isolated fixture
(a copy of scripts/, the plugin package, and the repo-root catalogs) and
runs ``scripts/validate.py`` as a subprocess so the assertions exercise
the real exit code and stdout the CI gate sees.

Covers the Codex dual-publish manifest checks added in issue 07
(secure-ship-0.4.4), which previously had no unit test — only the
parallel ``release.py`` logic was covered by ``test_release.py``. See
review item M4.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALIDATE = ROOT / "scripts" / "validate.py"


def _run(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*args], cwd=cwd, capture_output=True, text=True, check=False,
    )


class ValidateGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        shutil.copytree(ROOT / "scripts", self.root / "scripts")
        shutil.copytree(
            ROOT / "packages" / "design-playbook",
            self.root / "packages" / "design-playbook",
        )
        # validate.py reads the repo-root Claude marketplace catalog at
        # ROOT/.claude-plugin/marketplace.json and the Codex/agents catalog
        # at ROOT/.agents/plugins/marketplace.json (ADR-0009 dual-publish).
        shutil.copytree(ROOT / ".claude-plugin", self.root / ".claude-plugin")
        shutil.copytree(ROOT / ".agents", self.root / ".agents")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def validate(self) -> subprocess.CompletedProcess[str]:
        return _run(
            sys.executable, str(self.root / "scripts" / "validate.py"),
            cwd=self.root,
        )

    def test_clean_fixture_passes(self) -> None:
        # Regression guard: an unmodified copy of the shipped plugin must
        # pass the full static gate. If this fails, some other change
        # drifted the package out of spec and the FAIL cases below cannot
        # be trusted either.
        result = self.validate()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("VALIDATION PASSED", result.stdout)

    def test_codex_plugin_json_version_drift_fails(self) -> None:
        # Issue 07 acceptance: bump漏改 .codex-plugin/plugin.json ->
        # validate FAIL (gate catches Claude/Codex version drift).
        codex_plugin = (
            self.root / "packages" / "design-playbook" / ".codex-plugin" / "plugin.json"
        )
        payload = json.loads(codex_plugin.read_text(encoding="utf-8"))
        payload["version"] = "9.9.9"  # drift off Claude plugin.json
        codex_plugin.write_text(json.dumps(payload), encoding="utf-8")

        result = self.validate()

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("9.9.9", result.stdout)
        # FAIL line names both sides so the drift is visible at a glance.
        self.assertIn("matches Claude plugin.json", result.stdout)

    def test_codex_mcp_target_missing_fails(self) -> None:
        # Issue 07 acceptance: .codex-plugin/mcp.json points preview at
        # ./mcp/preview/server.py (resolved relative to its install cwd).
        # A missing target file would surface only at runtime in a foreign
        # agent; the static gate must catch it.
        codex_mcp = (
            self.root / "packages" / "design-playbook" / ".codex-plugin" / "mcp.json"
        )
        payload = json.loads(codex_mcp.read_text(encoding="utf-8"))
        payload["mcpServers"]["design-playbook-preview"]["args"] = [
            "./mcp/preview/missing.py"
        ]
        codex_mcp.write_text(json.dumps(payload), encoding="utf-8")

        result = self.validate()

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("target exists on disk", result.stdout)
        self.assertIn("./mcp/preview/missing.py", result.stdout)

    def test_agents_source_path_missing_fails(self) -> None:
        # Issue 07 acceptance: .agents/plugins/marketplace.json plugins[0]
        # .source.path must resolve to a real dir. A stale path ships a
        # broken install to Codex marketplace consumers.
        agents_market = self.root / ".agents" / "plugins" / "marketplace.json"
        payload = json.loads(agents_market.read_text(encoding="utf-8"))
        payload["plugins"][0]["source"]["path"] = "./packages/nonexistent"
        agents_market.write_text(json.dumps(payload), encoding="utf-8")

        result = self.validate()

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("source.path exists", result.stdout)
        self.assertIn("./packages/nonexistent", result.stdout)


if __name__ == "__main__":
    unittest.main()
