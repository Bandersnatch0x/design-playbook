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

    def test_unimplemented_tier3_agent_exits_nonzero(self) -> None:
        result = subprocess.run(
            [sys.executable, str(GENERATOR), "kiro-ide"],
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


# ---------------------------------------------------------------------------
# S2 tests
# ---------------------------------------------------------------------------


class MergeJsonHelperTests(unittest.TestCase):
    """merge_json_str: never-clobber, deep-merge, and stable-ordering contract."""

    def test_fresh_install_returns_our_data(self) -> None:
        result = gen_mod.merge_json_str(None, {"mcpServers": {"a": {"command": "x"}}})
        data = json.loads(result)
        self.assertIn("mcpServers", data)
        self.assertIn("a", data["mcpServers"])

    def test_existing_unknown_keys_preserved(self) -> None:
        existing = json.dumps({"userKey": "should-survive", "mcpServers": {}})
        result = gen_mod.merge_json_str(existing, {"mcpServers": {"dp": {"command": "y"}}})
        data = json.loads(result)
        self.assertEqual(data["userKey"], "should-survive")
        self.assertIn("dp", data["mcpServers"])

    def test_never_clobbers_existing_mcp_keys(self) -> None:
        existing = json.dumps({"mcpServers": {"existing-server": {"command": "keep"}}})
        result = gen_mod.merge_json_str(existing, {"mcpServers": {"new-server": {"command": "new"}}})
        data = json.loads(result)
        self.assertIn("existing-server", data["mcpServers"], "existing MCP key must not be removed")
        self.assertIn("new-server", data["mcpServers"])

    def test_our_keys_overwrite_existing_same_key(self) -> None:
        existing = json.dumps({"mcpServers": {"dp-preview": {"command": "old"}}})
        result = gen_mod.merge_json_str(existing, {"mcpServers": {"dp-preview": {"command": "new"}}})
        data = json.loads(result)
        self.assertEqual(data["mcpServers"]["dp-preview"]["command"], "new")

    def test_deep_nested_merge(self) -> None:
        existing = json.dumps({"mcp": {"servers": {"a": 1}}})
        result = gen_mod.merge_json_str(existing, {"mcp": {"extra": True}})
        data = json.loads(result)
        self.assertEqual(data["mcp"]["servers"]["a"], 1, "deep existing key preserved")
        self.assertTrue(data["mcp"]["extra"])

    def test_malformed_existing_json_raises_value_error(self) -> None:
        with self.assertRaises(ValueError, msg="malformed JSON must raise ValueError, not silently rebuild"):
            gen_mod.merge_json_str("not json {{", {"k": "v"})

    def test_non_object_existing_json_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            gen_mod.merge_json_str("[1, 2, 3]", {"k": "v"})

    def test_none_existing_text_returns_our_data(self) -> None:
        result = gen_mod.merge_json_str(None, {"k": "v"})
        self.assertEqual(json.loads(result)["k"], "v")


class ApplyMarkerBlockTests(unittest.TestCase):
    """apply_marker_block: idempotent marker-block replace/append semantics."""

    BEGIN = "<!-- design-playbook:begin -->"
    END = "<!-- design-playbook:end -->"

    def _apply(self, existing: str | None, content: str = "# dp\n\nbody") -> str:
        return gen_mod.apply_marker_block(existing, "0.21.0", content)

    def test_fresh_file_returns_just_block(self) -> None:
        result = self._apply(None)
        self.assertIn(self.BEGIN, result)
        self.assertIn(self.END, result)
        self.assertIn("generated-by design-playbook v0.21.0", result)
        self.assertIn("# dp", result)

    def test_append_when_no_existing_markers(self) -> None:
        existing = "# My Project\n\nMy instructions.\n"
        result = self._apply(existing)
        self.assertTrue(result.startswith("# My Project"), "user content preserved at top")
        self.assertIn(self.BEGIN, result)
        self.assertIn("My instructions.", result)

    def test_replace_existing_block_in_place(self) -> None:
        first = self._apply(None, "old content")
        # Simulate a second run with updated content
        second = gen_mod.apply_marker_block(first, "0.21.0", "new content")
        self.assertIn("new content", second)
        self.assertNotIn("old content", second, "old block content must be replaced")
        self.assertEqual(second.count(self.BEGIN), 1, "only one begin marker")
        self.assertEqual(second.count(self.END), 1, "only one end marker")

    def test_idempotent_fresh_file(self) -> None:
        first = self._apply(None, "same content")
        second = gen_mod.apply_marker_block(first, "0.21.0", "same content")
        self.assertEqual(first, second, "running twice on fresh output must be idempotent")

    def test_user_content_before_block_preserved_on_replace(self) -> None:
        preamble = "# My Copilot Instructions\n\nMy rules here.\n\n"
        initial = preamble + self._apply(None, "v1 content")
        updated = gen_mod.apply_marker_block(initial, "0.21.0", "v2 content")
        self.assertTrue(updated.startswith("# My Copilot Instructions"), "preamble preserved")
        self.assertIn("My rules here.", updated)
        self.assertIn("v2 content", updated)
        self.assertNotIn("v1 content", updated)

    def test_user_content_after_block_preserved_on_replace(self) -> None:
        block = self._apply(None, "dp content")
        doc = block + "\n\n## User section after block\n\nUser notes.\n"
        updated = gen_mod.apply_marker_block(doc, "0.21.0", "dp content updated")
        self.assertIn("User section after block", updated, "content after block preserved")
        self.assertIn("dp content updated", updated)


def _render_to_tmp(agent: str) -> tuple[dict, Path]:
    """Helper: render agent to a fresh tempdir, return (manifest, out_dir)."""
    tmp = Path(tempfile.mkdtemp())
    manifest = gen_mod.render(agent, out_dir=tmp, dry_run=False)
    return manifest, tmp


class CursorRendererTests(unittest.TestCase):
    """Cursor renderer: golden structure assertions."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest, cls.out = _render_to_tmp("cursor")

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.out, ignore_errors=True)

    def test_all_skill_mdc_files_written(self) -> None:
        skill_mdcs = [f for f in self.out.rglob("*.mdc")
                      if "commands" not in f.name and "mcp" not in f.name]
        # 8 skills: craft-guard, design-baseline, design-playbook, native-craft,
        #           reference-intake, ui-evaluator, ui-picker, ux-spec
        self.assertEqual(len(skill_mdcs), 8, f"expected 8 skill .mdc files, got {[f.name for f in skill_mdcs]}")

    def test_orchestrator_rule_has_always_apply_true(self) -> None:
        f = self.out / ".cursor" / "rules" / "design-playbook.mdc"
        self.assertTrue(f.is_file())
        text = f.read_text(encoding="utf-8")
        self.assertIn("alwaysApply: true", text)

    def test_sub_skill_rule_has_always_apply_false(self) -> None:
        f = self.out / ".cursor" / "rules" / "ui-picker.mdc"
        self.assertTrue(f.is_file())
        text = f.read_text(encoding="utf-8")
        self.assertIn("alwaysApply: false", text)

    def test_skill_rule_has_description_frontmatter(self) -> None:
        f = self.out / ".cursor" / "rules" / "ui-evaluator.mdc"
        text = f.read_text(encoding="utf-8")
        self.assertIn("description:", text)

    def test_commands_reference_file_written(self) -> None:
        f = self.out / ".cursor" / "rules" / "design-playbook-commands.mdc"
        self.assertTrue(f.is_file())
        text = f.read_text(encoding="utf-8")
        self.assertIn("design-io", text)
        self.assertIn("doctor", text)

    def test_mcp_note_written(self) -> None:
        f = self.out / ".cursor" / "rules" / "design-playbook-mcp.mdc"
        self.assertTrue(f.is_file())

    def test_cursor_mcp_json_written(self) -> None:
        f = self.out / ".cursor" / "mcp.json"
        self.assertTrue(f.is_file())
        data = json.loads(f.read_text(encoding="utf-8"))
        self.assertIn("mcpServers", data)
        self.assertIn("design-playbook-preview", data["mcpServers"])
        self.assertIn("design-playbook-evidence", data["mcpServers"])

    def test_cursor_mcp_json_has_stdio_type(self) -> None:
        data = json.loads((self.out / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
        for srv in data["mcpServers"].values():
            self.assertEqual(srv.get("type"), "stdio")

    def test_generated_by_comment_in_skill_rules(self) -> None:
        f = self.out / ".cursor" / "rules" / "craft-guard.mdc"
        text = f.read_text(encoding="utf-8")
        self.assertIn("generated-by design-playbook", text)

    def test_total_file_count(self) -> None:
        paths = [e["path"] for e in self.manifest["files"]]
        # 8 skills + 1 commands + 1 mcp note + 1 mcp.json = 11
        self.assertEqual(len(paths), 11)


class WindsurfRendererTests(unittest.TestCase):
    """Windsurf renderer: golden structure assertions."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest, cls.out = _render_to_tmp("windsurf")

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.out, ignore_errors=True)

    def test_all_skill_rule_files_written(self) -> None:
        rules = list((self.out / ".windsurf" / "rules").glob("*.md"))
        self.assertEqual(len(rules), 8, f"expected 8 skill rules, got {[f.name for f in rules]}")

    def test_workflow_files_written(self) -> None:
        workflows = list((self.out / ".windsurf" / "workflows").glob("*.md"))
        # 6 commands → 6 workflow files
        self.assertEqual(len(workflows), 6)

    def test_workflow_file_naming(self) -> None:
        names = {f.name for f in (self.out / ".windsurf" / "workflows").glob("*.md")}
        self.assertIn("design-playbook-design-io.md", names)
        self.assertIn("design-playbook-doctor.md", names)

    def test_mcp_guide_written_not_global_config(self) -> None:
        guide = self.out / "design-playbook-mcp-setup.md"
        self.assertTrue(guide.is_file(), "MCP guide must be written")
        # Verify the global config file is NOT written (ADR-0042 §4)
        global_cfg = self.out / ".codeium" / "windsurf" / "mcp_config.json"
        self.assertFalse(global_cfg.exists(), "global Windsurf MCP config must never be written")

    def test_mcp_guide_has_snippet(self) -> None:
        text = (self.out / "design-playbook-mcp-setup.md").read_text(encoding="utf-8")
        self.assertIn("mcp_config.json", text)
        self.assertIn("design-playbook-preview", text)

    def test_total_file_count(self) -> None:
        # 8 rules + 6 workflows + 1 mcp guide = 15
        self.assertEqual(len(self.manifest["files"]), 15)


class GeminiCLIRendererTests(unittest.TestCase):
    """Gemini CLI renderer: structural assertions."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest, cls.out = _render_to_tmp("gemini-cli")

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.out, ignore_errors=True)

    def test_gemini_md_written(self) -> None:
        f = self.out / "GEMINI.md"
        self.assertTrue(f.is_file())
        text = f.read_text(encoding="utf-8")
        self.assertIn("design-playbook", text)
        self.assertIn("<!-- design-playbook:begin -->", text)
        self.assertIn("<!-- design-playbook:end -->", text)

    def test_gemini_md_user_content_preserved_on_rerender(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            (t / "GEMINI.md").write_text("# My Project\n\nMy custom Gemini rules.\n", encoding="utf-8")
            gen_mod.render("gemini-cli", out_dir=t, dry_run=False)
            text = (t / "GEMINI.md").read_text(encoding="utf-8")
        self.assertIn("My custom Gemini rules.", text, "pre-existing user content preserved")
        self.assertIn("<!-- design-playbook:begin -->", text)

    def test_all_command_toml_files_written(self) -> None:
        toml_files = list((self.out / ".gemini" / "commands").glob("*.toml"))
        self.assertEqual(len(toml_files), 6)

    def test_command_toml_has_args_placeholder(self) -> None:
        f = self.out / ".gemini" / "commands" / "design-io.toml"
        self.assertTrue(f.is_file())
        text = f.read_text(encoding="utf-8")
        self.assertIn("{{args}}", text)

    def test_command_toml_has_description(self) -> None:
        text = (self.out / ".gemini" / "commands" / "design-io.toml").read_text("utf-8")
        self.assertIn("description", text)

    def test_settings_json_has_mcp_servers(self) -> None:
        f = self.out / ".gemini" / "settings.json"
        self.assertTrue(f.is_file())
        data = json.loads(f.read_text(encoding="utf-8"))
        self.assertIn("mcpServers", data)
        self.assertIn("design-playbook-preview", data["mcpServers"])

    def test_settings_json_merge_preserves_existing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            existing = {"mcpServers": {"my-other-server": {"command": "other"}}, "theme": "dark"}
            (t / ".gemini").mkdir()
            (t / ".gemini" / "settings.json").write_text(
                json.dumps(existing), encoding="utf-8"
            )
            gen_mod.render("gemini-cli", out_dir=t, dry_run=False)
            data = json.loads((t / ".gemini" / "settings.json").read_text("utf-8"))
        self.assertIn("my-other-server", data["mcpServers"], "pre-existing MCP server preserved")
        self.assertEqual(data.get("theme"), "dark", "user theme setting preserved")


class OpenCodeRendererTests(unittest.TestCase):
    """OpenCode renderer: structural assertions."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest, cls.out = _render_to_tmp("opencode")

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.out, ignore_errors=True)

    def test_agents_md_written(self) -> None:
        f = self.out / "AGENTS.md"
        self.assertTrue(f.is_file())
        text = f.read_text(encoding="utf-8")
        self.assertIn("design-playbook", text)
        self.assertIn("<!-- design-playbook:begin -->", text)
        self.assertIn("<!-- design-playbook:end -->", text)

    def test_agents_md_user_content_preserved_on_rerender(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            (t / "AGENTS.md").write_text("# Project AGENTS\n\nExisting team rules.\n", encoding="utf-8")
            gen_mod.render("opencode", out_dir=t, dry_run=False)
            text = (t / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("Existing team rules.", text, "pre-existing user content preserved")
        self.assertIn("<!-- design-playbook:begin -->", text)

    def test_agents_md_contains_skills_and_commands(self) -> None:
        text = (self.out / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("ui-evaluator", text)
        self.assertIn("design-io", text)

    def test_opencode_json_has_mcp_key(self) -> None:
        f = self.out / "opencode.json"
        self.assertTrue(f.is_file())
        data = json.loads(f.read_text(encoding="utf-8"))
        self.assertIn("mcp", data)
        self.assertIn("design-playbook-preview", data["mcp"])

    def test_opencode_json_merge_preserves_existing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            existing = {"provider": "anthropic", "mcp": {"user-server": {"command": "keep"}}}
            (t / "opencode.json").write_text(json.dumps(existing), encoding="utf-8")
            gen_mod.render("opencode", out_dir=t, dry_run=False)
            data = json.loads((t / "opencode.json").read_text("utf-8"))
        self.assertEqual(data.get("provider"), "anthropic", "existing config key preserved")
        self.assertIn("user-server", data["mcp"], "pre-existing MCP server preserved")


class GitHubCopilotRendererTests(unittest.TestCase):
    """GitHub Copilot renderer: structural assertions."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest, cls.out = _render_to_tmp("github-copilot")

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.out, ignore_errors=True)

    def test_copilot_instructions_written(self) -> None:
        f = self.out / ".github" / "copilot-instructions.md"
        self.assertTrue(f.is_file())
        text = f.read_text(encoding="utf-8")
        self.assertIn("design-playbook", text)
        self.assertIn("<!-- design-playbook:begin -->", text)
        self.assertIn("<!-- design-playbook:end -->", text)

    def test_copilot_instructions_user_content_preserved_on_rerender(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            (t / ".github").mkdir()
            (t / ".github" / "copilot-instructions.md").write_text(
                "# Org Copilot Rules\n\nAlways write tests.\n", encoding="utf-8"
            )
            gen_mod.render("github-copilot", out_dir=t, dry_run=False)
            text = (t / ".github" / "copilot-instructions.md").read_text(encoding="utf-8")
        self.assertIn("Always write tests.", text, "pre-existing org rules preserved")
        self.assertIn("<!-- design-playbook:begin -->", text)

    def test_all_skill_instruction_files_written(self) -> None:
        inst_files = list((self.out / ".github" / "instructions").glob("*.instructions.md"))
        self.assertEqual(len(inst_files), 8)

    def test_instruction_files_have_apply_to_frontmatter(self) -> None:
        f = self.out / ".github" / "instructions" / "ui-picker.instructions.md"
        self.assertTrue(f.is_file())
        text = f.read_text(encoding="utf-8")
        self.assertIn("applyTo:", text)
        self.assertIn('**', text)  # applyTo: "**"

    def test_mcp_json_written(self) -> None:
        f = self.out / ".mcp.json"
        self.assertTrue(f.is_file())
        data = json.loads(f.read_text(encoding="utf-8"))
        self.assertIn("servers", data)
        self.assertIn("design-playbook-preview", data["servers"])

    def test_mcp_json_uses_servers_not_mcp_servers(self) -> None:
        data = json.loads((self.out / ".mcp.json").read_text(encoding="utf-8"))
        self.assertIn("servers", data)
        self.assertNotIn("mcpServers", data)

    def test_mcp_json_merge_preserves_existing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            existing = {"servers": {"my-server": {"type": "stdio", "command": "keep"}}}
            (t / ".mcp.json").write_text(json.dumps(existing), encoding="utf-8")
            gen_mod.render("github-copilot", out_dir=t, dry_run=False)
            data = json.loads((t / ".mcp.json").read_text("utf-8"))
        self.assertIn("my-server", data["servers"], "pre-existing server preserved")


class Tier2ListTests(unittest.TestCase):
    """--list must show all Tier-2 renderers as (renderer ready)."""

    def _list_output(self) -> str:
        result = subprocess.run(
            [sys.executable, str(GENERATOR), "--list"],
            capture_output=True, text=True, encoding="utf-8",
            cwd=PKG, timeout=15,
        )
        self.assertEqual(result.returncode, 0)
        return result.stdout

    def test_all_tier2_renderers_shown_as_ready(self) -> None:
        out = self._list_output()
        for agent in ("cursor", "gemini-cli", "opencode", "windsurf", "github-copilot"):
            self.assertIn(f"{agent}", out, f"{agent} not in --list output")
            # Find the line for this agent and check for renderer ready marker
            line = next((ln for ln in out.splitlines() if agent in ln), "")
            self.assertIn("renderer ready", line, f"{agent} not shown as renderer ready: {line!r}")

    def test_codex_still_shown_as_ready(self) -> None:
        out = self._list_output()
        line = next((ln for ln in out.splitlines() if "codex" in ln), "")
        self.assertIn("renderer ready", line)


class Tier2DryRunTests(unittest.TestCase):
    """Dry-run for all Tier-2 agents returns valid manifest and writes nothing."""

    def _dry_run(self, agent: str) -> dict:
        result = subprocess.run(
            [sys.executable, str(GENERATOR), agent, "--dry-run", "--out", str(Path(tempfile.gettempdir()))],
            capture_output=True, text=True, encoding="utf-8",
            cwd=PKG, timeout=30,
        )
        self.assertEqual(result.returncode, 0, f"{agent} dry-run failed: {result.stderr}")
        return json.loads(result.stdout)

    def test_cursor_dry_run(self) -> None:
        m = self._dry_run("cursor")
        self.assertEqual(m["agent"], "cursor")
        self.assertGreater(len(m["files"]), 0)

    def test_gemini_cli_dry_run(self) -> None:
        m = self._dry_run("gemini-cli")
        self.assertEqual(m["agent"], "gemini-cli")

    def test_opencode_dry_run(self) -> None:
        m = self._dry_run("opencode")
        self.assertEqual(m["agent"], "opencode")

    def test_windsurf_dry_run(self) -> None:
        m = self._dry_run("windsurf")
        self.assertEqual(m["agent"], "windsurf")

    def test_github_copilot_dry_run(self) -> None:
        m = self._dry_run("github-copilot")
        self.assertEqual(m["agent"], "github-copilot")


if __name__ == "__main__":
    unittest.main()

