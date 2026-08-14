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
        encoding="utf-8", errors="replace",
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
        # The dsh-design-playbook thin bundle is a separate package that
        # validate.py checks for P2 MCP bridge consistency.
        shutil.copytree(
            ROOT / "packages" / "dsh-design-playbook",
            self.root / "packages" / "dsh-design-playbook",
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

    def test_missing_public_package_reference_fails(self) -> None:
        readme = self.root / "packages" / "design-playbook" / "README.md"
        with readme.open("a", encoding="utf-8") as handle:
            handle.write("\nRun `scripts/missing-public-tool.py`.\n")

        result = self.validate()

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("README.md", result.stdout)
        self.assertIn("scripts/missing-public-tool.py", result.stdout)
        self.assertIn("target exists", result.stdout)

    def test_existing_but_unpublished_package_reference_fails(self) -> None:
        package_json = self.root / "packages" / "design-playbook" / "package.json"
        payload = json.loads(package_json.read_text(encoding="utf-8"))
        payload["files"] = [entry for entry in payload["files"] if entry != "scripts"]
        package_json.write_text(json.dumps(payload), encoding="utf-8")

        result = self.validate()

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("skills/design-playbook/SKILL.md", result.stdout)
        self.assertIn("scripts/validate_run.py", result.stdout)
        self.assertIn("included by package.json files[]", result.stdout)

    def test_non_package_references_are_ignored(self) -> None:
        readme = self.root / "packages" / "design-playbook" / "README.md"
        with readme.open("a", encoding="utf-8") as handle:
            handle.write(
                "\nIgnore `https://example.com/scripts/tool.py`, "
                "`.scratch/<run>/evidence/result.json`, `src/app.py`, and "
                "[host source](src/app.py).\n"
            )

        result = self.validate()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("VALIDATION PASSED", result.stdout)

    def test_skill_heading_rename_fails_named_prose_gate(self) -> None:
        evaluator = (
            self.root / "packages" / "design-playbook" / "skills"
            / "ui-evaluator" / "SKILL.md"
        )
        text = evaluator.read_text(encoding="utf-8")
        self.assertIn("### 4. Verdict", text)
        evaluator.write_text(
            text.replace("### 4. Verdict", "### 4. Final verdict", 1),
            encoding="utf-8",
        )

        result = self.validate()

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("ui-evaluator blocks unattended acceptance", result.stdout)
        self.assertIn("VALIDATION FAILED", result.stdout)

    def test_registry_enum_drift_fails(self) -> None:
        # G8 product-level: an invalid enum value on any registry entry must
        # fail the static gate (rules-prototype §8.2 machine face).
        registry = (
            self.root / "packages" / "design-playbook" / "skills"
            / "design-playbook" / "references" / "rules.md"
        )
        text = registry.read_text(encoding="utf-8")
        self.assertIn("id: CRAFT-01", text)
        registry.write_text(
            text.replace("status: advisory", "status: suggested", 1),
            encoding="utf-8",
        )

        result = self.validate()

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("G8 CRAFT-01 entry valid", result.stdout)
        self.assertIn("VALIDATION FAILED", result.stdout)

    def test_registry_reference_drift_fails(self) -> None:
        # G8 reference existence: related/overrides/supersedes must resolve
        # to registry ids with pinned versions.
        registry = (
            self.root / "packages" / "design-playbook" / "skills"
            / "design-playbook" / "references" / "rules.md"
        )
        text = registry.read_text(encoding="utf-8")
        self.assertIn("related: CRAFT-06@1", text)
        registry.write_text(
            text.replace("related: CRAFT-06@1", "related: CRAFT-99@1", 1),
            encoding="utf-8",
        )

        result = self.validate()

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("references unknown id CRAFT-99", result.stdout)
        self.assertIn("VALIDATION FAILED", result.stdout)

    def test_craft_not_applicable_reason_drift_fails(self) -> None:
        # Seven-column migration: a blank not-applicable reason is invalid
        # (the old blank-N/A discipline carried into the three-state split).
        fixture = (
            self.root / "packages" / "design-playbook" / "examples"
            / "craft-detectors" / "saas-dashboard.md"
        )
        text = fixture.read_text(encoding="utf-8")
        marker = "Surface declares one restrained standard control radius"
        self.assertIn(marker, text)
        fixture.write_text(
            text.replace(
                "Surface declares one restrained standard control radius in "
                "design tokens; no pill or shape-geometry variation face is "
                "in scope",
                "-",
                1,
            ),
            encoding="utf-8",
        )

        result = self.validate()

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("observable reason", result.stdout)
        self.assertIn("VALIDATION FAILED", result.stdout)

    def test_composition_detector_coverage_drift_fails(self) -> None:
        fixture = (
            self.root / "packages" / "design-playbook" / "examples"
            / "craft-detectors" / "composition-contrast.md"
        )
        text = fixture.read_text(encoding="utf-8")
        target = "| card-collection-clear | CRAFT-02@1 | applicable | - | clear |"
        self.assertIn(target, text)
        fixture.write_text(text.replace(target, "| card-collection-clear | CRAFT-02@1 | applicable | - | hit |", 1), encoding="utf-8")

        result = self.validate()

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("CRAFT-02 contrast has hit and clear", result.stdout)
        self.assertIn("VALIDATION FAILED", result.stdout)

    def test_craft_baseline_exception_drift_fails(self) -> None:
        fixture = (
            self.root / "packages" / "design-playbook" / "examples"
            / "craft-detectors" / "existing-brand-contrast.md"
        )
        text = fixture.read_text(encoding="utf-8")
        marker = "Baseline disposition: clear"
        self.assertIn(marker, text)
        fixture.write_text(text.replace(marker, "Baseline disposition: hit", 1), encoding="utf-8")

        result = self.validate()

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("verified baseline wins generic detector taste", result.stdout)
        self.assertIn("VALIDATION FAILED", result.stdout)

    def test_evaluator_craft_ledger_contract_drift_fails(self) -> None:
        evaluator = (
            self.root / "packages" / "design-playbook" / "skills"
            / "ui-evaluator" / "SKILL.md"
        )
        text = evaluator.read_text(encoding="utf-8")
        self.assertIn("`.scratch/<run>/craft-guard.md`", text)
        evaluator.write_text(
            text.replace("`.scratch/<run>/craft-guard.md`", "`.scratch/<run>/craft.md`", 1),
            encoding="utf-8",
        )

        result = self.validate()

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("ui-evaluator consumes craft registry audit rows", result.stdout)
        self.assertIn("VALIDATION FAILED", result.stdout)

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

    def test_dsh_dependency_version_drift_fails(self) -> None:
        dsh_package = (
            self.root / "packages" / "dsh-design-playbook" / "package.json"
        )
        payload = json.loads(dsh_package.read_text(encoding="utf-8"))
        payload["dependencies"]["design-playbook"] = "^0.13.0"
        dsh_package.write_text(json.dumps(payload), encoding="utf-8")

        result = self.validate()

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(
            "dsh-design-playbook dependency on design-playbook '^0.13.0'",
            result.stdout,
        )
        self.assertIn("VALIDATION FAILED", result.stdout)

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
    def test_extra_command_without_version_admission_fails(self) -> None:
        # OPP-01 / ADR-0015: main must never expose unreleased capability
        # under a released version. A 4th command while plugin.json still
        # declares 0.9.x must fail the gate.
        fake = (
            self.root / "packages" / "design-playbook" / "commands"
            / "fake-review.md"
        )
        fake.write_text(
            "---\ndescription: hypothetical fourth command\n---\nbody\n",
            encoding="utf-8",
        )

        result = self.validate()

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("expects commands", result.stdout)
        self.assertIn("VALIDATION FAILED", result.stdout)


if __name__ == "__main__":
    unittest.main()
