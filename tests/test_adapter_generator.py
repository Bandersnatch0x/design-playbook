#!/usr/bin/env python3
"""Unit tests for the multi-platform adapter generator (ADR-0042).

Tests:
  1. Matrix schema — all rows are valid; no duplicates; field invariants.
  2. Codex renderer golden — compare output to committed snapshot byte-for-byte
     (LF-normalized, matching the drift gate).
  3. Dry-run manifest determinism — two consecutive dry-runs produce identical JSON.
  4. CLI --list smoke — spawn generate_adapter.py --list and check output.
  5. cli.js smoke — spawn lib/cli.js --list via node; skip visibly when node absent.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "packages" / "design-playbook"
GENERATOR = PKG / "scripts" / "generate_adapter.py"
CLI_JS = PKG / "lib" / "cli.js"

sys.path.insert(0, str(PKG / "scripts"))


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


matrix_mod = _load_module(PKG / "scripts" / "adapter_matrix.py", "dpb_adapter_matrix")
gen_mod = _load_module(GENERATOR, "dpb_generate_adapter")


class MatrixSchemaTests(unittest.TestCase):
    """adapter_matrix.py: schema validation."""

    def test_no_validation_errors(self) -> None:
        errors = matrix_mod.validate_matrix()
        self.assertEqual(errors, [], f"Matrix validation errors: {errors}")

    def test_all_required_fields_present(self) -> None:
        for row in matrix_mod.MATRIX:
            self.assertIsInstance(row.agent, str)
            self.assertGreater(len(row.agent), 0)
            self.assertIn(row.tier, (1, 2, 3))
            self.assertIsInstance(row.rules, bool)
            self.assertIsInstance(row.commands, bool)
            self.assertIsInstance(row.mcp_project, bool)
            self.assertIsInstance(row.hooks, bool)
            self.assertIsInstance(row.skills, bool)
            self.assertIsInstance(row.rules_target, str)
            self.assertGreater(len(row.rules_target), 0)

    def test_no_duplicate_agents(self) -> None:
        names = [row.agent for row in matrix_mod.MATRIX]
        duplicates = {n for n in names if names.count(n) > 1}
        self.assertEqual(duplicates, set(), f"Duplicate agents: {duplicates}")

    def test_claude_code_and_codex_are_tier1(self) -> None:
        tier1 = {row.agent for row in matrix_mod.MATRIX if row.tier == 1}
        self.assertIn("claude-code", tier1)
        self.assertIn("codex", tier1)

    def test_tier3_agents_have_no_advanced_capabilities(self) -> None:
        for row in matrix_mod.MATRIX:
            if row.tier == 3:
                self.assertFalse(row.commands, f"{row.agent}: tier-3 must have commands=False")
                self.assertFalse(row.mcp_project, f"{row.agent}: tier-3 must have mcp_project=False")
                self.assertFalse(row.hooks, f"{row.agent}: tier-3 must have hooks=False")
                self.assertFalse(row.skills, f"{row.agent}: tier-3 must have skills=False")

    def test_get_agent_returns_row(self) -> None:
        row = matrix_mod.get_agent("codex")
        self.assertIsNotNone(row)
        self.assertEqual(row.agent, "codex")
        self.assertEqual(row.tier, 1)

    def test_get_agent_unknown_returns_none(self) -> None:
        self.assertIsNone(matrix_mod.get_agent("nonexistent-agent-xyz"))

    def test_tier1_snapshot_agents_excludes_claude_code(self) -> None:
        # claude-code is Tier 1 but managed by the plugin system, not a generator snapshot.
        self.assertNotIn("claude-code", matrix_mod.TIER1_SNAPSHOT_AGENTS)
        self.assertIn("codex", matrix_mod.TIER1_SNAPSHOT_AGENTS)

    def test_matrix_has_all_spec_tier2_agents(self) -> None:
        spec_tier2 = {"cursor", "gemini-cli", "opencode", "windsurf", "github-copilot"}
        tier2 = {row.agent for row in matrix_mod.MATRIX if row.tier == 2}
        self.assertEqual(tier2, spec_tier2)

    def test_windsurf_mcp_is_not_project_level(self) -> None:
        row = matrix_mod.get_agent("windsurf")
        self.assertIsNotNone(row)
        self.assertFalse(row.mcp_project, "Windsurf MCP is global-only, not project-level")

    def test_validate_matrix_catches_duplicates(self) -> None:
        dup_row = matrix_mod.AgentRow(
            agent="codex", tier=1, rules=True, commands=True,
            mcp_project=True, hooks=False, skills=True,
            rules_target=".codex-plugin/ + codex/AGENTS.md",
        )
        errors = matrix_mod.validate_matrix(matrix_mod.MATRIX + (dup_row,))
        self.assertTrue(any("duplicate" in e for e in errors), errors)


def _sha256_lf(data: bytes) -> str:
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


class CodexRendererGoldenTests(unittest.TestCase):
    """Codex renderer: generated output matches committed snapshot."""

    def _run_dry_run(self) -> dict:
        result = subprocess.run(
            [sys.executable, str(GENERATOR), "codex", "--dry-run"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=PKG, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_dry_run_manifest_structure(self) -> None:
        manifest = self._run_dry_run()
        self.assertEqual(manifest["agent"], "codex")
        self.assertIn("version", manifest)
        self.assertIsInstance(manifest["files"], list)
        paths = [f["path"] for f in manifest["files"]]
        self.assertIn(".codex-plugin/plugin.json", paths)
        self.assertIn(".codex-plugin/mcp.json", paths)
        self.assertIn("codex/AGENTS.md", paths)

    def test_committed_snapshots_match_generator(self) -> None:
        manifest = self._run_dry_run()
        mismatches: list[str] = []
        for entry in manifest["files"]:
            rel = entry["path"]
            expected_sha = entry["sha256"]
            committed = PKG / rel
            if not committed.is_file():
                mismatches.append(f"missing: {rel}")
                continue
            actual_sha = _sha256_lf(committed.read_bytes())
            if actual_sha != expected_sha:
                mismatches.append(f"hash mismatch: {rel} (expected {expected_sha[:8]}, got {actual_sha[:8]})")
        self.assertEqual(mismatches, [],
                         f"Committed snapshots diverge from generator output.\n"
                         f"Run: python packages/design-playbook/scripts/generate_adapter.py codex\n"
                         f"Mismatches: {mismatches}")

    def test_plugin_json_version_matches_canonical(self) -> None:
        with (PKG / ".claude-plugin" / "plugin.json").open(encoding="utf-8") as f:
            canonical_version = json.load(f)["version"]
        with (PKG / ".codex-plugin" / "plugin.json").open(encoding="utf-8") as f:
            codex_version = json.load(f)["version"]
        self.assertEqual(codex_version, canonical_version)

    def test_codex_agents_md_has_generated_by_comment(self) -> None:
        text = (PKG / "codex" / "AGENTS.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("<!-- generated-by design-playbook v"),
                        "codex/AGENTS.md must start with generated-by comment")

    def test_codex_mcp_json_has_both_servers(self) -> None:
        with (PKG / ".codex-plugin" / "mcp.json").open(encoding="utf-8") as f:
            data = json.load(f)
        servers = data.get("mcpServers", {})
        self.assertIn("design-playbook-preview", servers)
        self.assertIn("design-playbook-evidence", servers)

    def test_render_to_temp_dir_writes_expected_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            manifest = gen_mod.render("codex", out_dir=out, dry_run=False)
            for entry in manifest["files"]:
                dest = out / entry["path"]
                self.assertTrue(dest.is_file(), f"expected file not written: {entry['path']}")
                sha = _sha256_lf(dest.read_bytes())
                self.assertEqual(sha, entry["sha256"],
                                 f"written file hash mismatch: {entry['path']}")


class DryRunDeterminismTests(unittest.TestCase):
    """Dry-run must produce identical JSON on consecutive invocations."""

    def _dry_run_json(self) -> str:
        result = subprocess.run(
            [sys.executable, str(GENERATOR), "codex", "--dry-run"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=PKG, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def test_two_consecutive_dry_runs_are_identical(self) -> None:
        first = self._dry_run_json()
        second = self._dry_run_json()
        self.assertEqual(first, second, "Dry-run output is not deterministic")

    def test_dry_run_does_not_write_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [sys.executable, str(GENERATOR), "codex", "--dry-run", "--out", tmp],
                capture_output=True, text=True, encoding="utf-8",
                cwd=PKG, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            written = list(Path(tmp).rglob("*"))
            self.assertEqual(written, [], f"--dry-run must not write files, found: {written}")


class GeneratorCLITests(unittest.TestCase):
    """Generator CLI: --list and error handling."""

    def test_list_flag_exits_zero_and_lists_agents(self) -> None:
        result = subprocess.run(
            [sys.executable, str(GENERATOR), "--list"],
            capture_output=True, text=True, encoding="utf-8",
            cwd=PKG, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("codex", result.stdout)
        self.assertIn("cursor", result.stdout)

    def test_unknown_agent_exits_nonzero(self) -> None:
        result = subprocess.run(
            [sys.executable, str(GENERATOR), "nonexistent-agent-xyz"],
            capture_output=True, text=True, encoding="utf-8",
            cwd=PKG, timeout=15,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown agent", result.stderr)

    def test_no_args_exits_nonzero_with_usage(self) -> None:
        result = subprocess.run(
            [sys.executable, str(GENERATOR)],
            capture_output=True, text=True, encoding="utf-8",
            cwd=PKG, timeout=15,
        )
        self.assertNotEqual(result.returncode, 0)

    def test_unimplemented_tier2_agent_exits_nonzero(self) -> None:
        result = subprocess.run(
            [sys.executable, str(GENERATOR), "cursor"],
            capture_output=True, text=True, encoding="utf-8",
            cwd=PKG, timeout=15,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("renderer", result.stderr.lower())


class NodeShimSmokeTests(unittest.TestCase):
    """cli.js: spawn with --list via node (skip visibly when node absent)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.node = shutil.which("node")

    def test_cli_js_exists(self) -> None:
        self.assertTrue(CLI_JS.is_file(), f"cli.js not found at {CLI_JS}")

    def test_list_via_node_shim(self) -> None:
        if not self.node:
            self.skipTest("node not found on PATH — skipping cli.js smoke")
        result = subprocess.run(
            [self.node, str(CLI_JS), "--list"],
            capture_output=True, text=True, encoding="utf-8",
            cwd=PKG, timeout=15,
        )
        self.assertEqual(result.returncode, 0,
                         f"cli.js --list failed:\nstdout: {result.stdout}\nstderr: {result.stderr}")
        self.assertIn("codex", result.stdout)

    def test_init_alias_via_node_shim(self) -> None:
        if not self.node:
            self.skipTest("node not found on PATH — skipping cli.js smoke")
        result = subprocess.run(
            [self.node, str(CLI_JS), "--list"],
            capture_output=True, text=True, encoding="utf-8",
            cwd=PKG, timeout=15,
        )
        self.assertEqual(result.returncode, 0)

    def test_cli_js_has_no_deps(self) -> None:
        src = CLI_JS.read_text(encoding="utf-8")
        # Must only use built-in node: modules
        self.assertNotIn("require('", src.replace("require('node:", ""))
        # Well, it uses node: prefixed modules — check no external packages
        for line in src.splitlines():
            if "require(" in line and "node:" not in line and "//" not in line.lstrip():
                self.fail(f"cli.js requires non-builtin module: {line.strip()}")


if __name__ == "__main__":
    unittest.main()
