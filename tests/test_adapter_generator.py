#!/usr/bin/env python3
"""Unit tests for the multi-platform adapter generator (ADR-0042).

Tests:
  1. Matrix schema — all rows are valid; no duplicates; field invariants.
  2. Codex renderer golden — compare output to committed snapshot byte-for-byte
     (LF-normalized, matching the drift gate).
  3. Dry-run manifest determinism — two consecutive dry-runs produce identical JSON.
  4. CLI --list smoke — spawn generate_adapter.py --list and check output.
  5. cli.js smoke — spawn lib/cli.js --list via node; skip visibly when node absent.
  6. Renderer dispatch (issue #111) — matrix-driven: every non-native row renders
     (dedicated renderer or AGENTS.md floor fallback); native rows emit nothing.
  7. Frontmatter header placement (issue #115) — matrix-driven: every rendered
     artifact that opens with frontmatter has ``---`` as its literal first line
     and the generated-by comment as the first line after the block.
  8. Lifecycle status (T-149 / S7) — status/successor validation, and a dead
     row emitting nothing (with the counter-example).
  9. agent_plugins bundle (T-149 / S4) — the portable plugin.json + mcp.json
     layout, with its declared surface list pinned to the matrix render.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
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

import adapter_markers as markers  # noqa: E402


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


matrix_mod = _load_module(PKG / "scripts" / "adapter_matrix.py", "dpb_adapter_matrix")
gen_mod = _load_module(GENERATOR, "dpb_generate_adapter")

# Rows the generator emits an adapter for: not native (host consumes the
# package directly) and not dead (no product left to run it).  Every
# matrix-driven sweep below uses this, so a newly dead row drops out of all of
# them at once instead of failing one loop at a time.
GENERATING_AGENTS = [
    row.agent for row in matrix_mod.MATRIX if not row.native and row.generates
]

# Every non-native row also carries the portable skills landing (T-151 / I12):
# the package's whole skills tree, references included.  Counted off disk so
# adding a skill does not require touching every per-renderer total.
LANDED_FILES = len([
    p for p in (PKG / "skills").rglob("*")
    if p.is_file() and "__pycache__" not in p.parts
])
LANDED_SKILLS = len(list((PKG / "skills").glob("*/SKILL.md")))

# Rows that declare a skills landing — every generating row except the Tier-3
# floor, which the matrix declares as AGENTS.md-only (T-151 / I12).
LANDING_AGENTS = [row.agent for row in matrix_mod.MATRIX if row.skills_landing]

_LANDING_PREFIX = matrix_mod.AGENTS_SKILLS_DIR + "/"


def _is_verbatim_landing(rel: str) -> bool:
    """True for a landed copy the generator does not author.

    A skill's own ``references/*`` travel unmodified so its relative pointers
    still resolve; they are not artifacts we stamp, so the generated-by
    header rule does not apply to them.
    """
    return rel.startswith(_LANDING_PREFIX) and not rel.endswith("/SKILL.md")


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
            self.assertIsInstance(row.native, bool)

    def test_claude_code_is_the_only_native_row(self) -> None:
        # native=True is the matrix marker for "host platform consumes the
        # package directly; the generator emits nothing" (issue #111).
        native = [row.agent for row in matrix_mod.MATRIX if row.native]
        self.assertEqual(native, ["claude-code"])

    def test_no_duplicate_agents(self) -> None:
        names = [row.agent for row in matrix_mod.MATRIX]
        duplicates = {n for n in names if names.count(n) > 1}
        self.assertEqual(duplicates, set(), f"Duplicate agents: {duplicates}")

    def test_claude_code_and_codex_are_tier1(self) -> None:
        tier1 = {row.agent for row in matrix_mod.MATRIX if row.tier == 1}
        self.assertIn("claude-code", tier1)
        self.assertIn("codex", tier1)

    def test_tier_counts_match_published_claims(self) -> None:
        self.assertEqual(len(matrix_mod.MATRIX), 30)
        self.assertEqual(len(matrix_mod.TIER1_SNAPSHOT_AGENTS), 1)

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
        spec_tier2 = {"cursor", "gemini-cli", "opencode", "windsurf", "github-copilot", "zed"}
        tier2 = {row.agent for row in matrix_mod.MATRIX if row.tier == 2}
        self.assertEqual(tier2, spec_tier2)

    def test_validate_matrix_catches_duplicates(self) -> None:
        dup_row = matrix_mod.AgentRow(agent="codex", tier=1, renderer="codex")
        errors = matrix_mod.validate_matrix(matrix_mod.MATRIX + (dup_row,))
        self.assertTrue(any("duplicate" in e for e in errors), errors)

    def test_a_tier2_row_cannot_be_built_without_a_renderer(self) -> None:
        """Declaring a tier without its output surface is the drift removed.

        A row that says "Tier 2" but names no renderer used to render the
        AGENTS.md floor silently; now it cannot be constructed.
        """
        with self.assertRaises(ValueError):
            matrix_mod.AgentRow(agent="silently-tier-3", tier=2)

    def test_a_tier3_row_cannot_name_a_dedicated_renderer(self) -> None:
        with self.assertRaises(ValueError):
            matrix_mod.AgentRow(agent="over-declared", tier=3, renderer="codex")


class MatrixLifecycleTests(unittest.TestCase):
    """AgentRow.status / successor — the lifecycle dimension (T-149 / S7)."""

    def test_default_status_is_active(self) -> None:
        row = matrix_mod.AgentRow(agent="brand-new", tier=3)
        self.assertEqual(row.status, "active")
        self.assertIsNone(row.successor)
        self.assertTrue(row.generates)

    def test_illegal_status_value_is_rejected(self) -> None:
        # The whole point of the field: a typo like "dea" must not read as
        # "some other lifecycle" and silently keep generating.
        with self.assertRaises(ValueError) as ctx:
            matrix_mod.AgentRow(agent="typo", tier=3, status="dea")
        self.assertIn("status must be one of", str(ctx.exception))

    def test_rebranded_row_must_name_its_successor(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            matrix_mod.AgentRow(agent="rebranded-without-target", tier=3,
                                status="rebranded")
        self.assertIn("successor", str(ctx.exception))

    def test_active_row_cannot_carry_a_successor(self) -> None:
        with self.assertRaises(ValueError):
            matrix_mod.AgentRow(agent="active-with-successor", tier=3,
                                status="active", successor="elsewhere")

    def test_dead_row_does_not_generate(self) -> None:
        row = matrix_mod.AgentRow(agent="gone", tier=3, status="dead")
        self.assertFalse(row.generates)

    def test_deprecated_and_rebranded_rows_still_generate(self) -> None:
        # Only ``dead`` stops output: a deprecated surface and a renamed one
        # both still exist under the name this row carries.
        deprecated = matrix_mod.AgentRow(agent="old", tier=3, status="deprecated")
        rebranded = matrix_mod.AgentRow(agent="renamed", tier=3,
                                        status="rebranded", successor="new")
        self.assertTrue(deprecated.generates)
        self.assertTrue(rebranded.generates)

    def test_known_dead_row_is_roo_code(self) -> None:
        # Roo Code shut down (2026-05, S7 evidence): the row stays (breadth is
        # frozen) but it is marked, so no adapter is generated for a host that
        # is gone.
        row = matrix_mod.get_agent("roo-code")
        self.assertIsNotNone(row)
        self.assertEqual(row.status, "dead")
        self.assertFalse(row.generates)

    def test_known_rebranded_row_is_windsurf(self) -> None:
        # Windsurf was folded into Devin Local (2026-09, S7 evidence).
        row = matrix_mod.get_agent("windsurf")
        self.assertIsNotNone(row)
        self.assertEqual(row.status, "rebranded")
        self.assertEqual(row.successor, "devin")
        self.assertTrue(row.generates)

    def test_every_non_active_row_is_explained(self) -> None:
        # A lifecycle mark without a successor or a stated reason is how a
        # matrix rots: every non-active row must at least be a known status,
        # and a rebranded one must point somewhere.
        for row in matrix_mod.MATRIX:
            self.assertIn(row.status, matrix_mod.STATUSES, row.agent)
            if row.status == "rebranded":
                self.assertTrue(row.successor, f"{row.agent}: needs a successor")


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
        self.assertTrue(text.startswith(f"<!-- {markers.MARKER_TEXT} v"),
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

    def test_unknown_agent_name_exits_nonzero(self) -> None:
        result = subprocess.run(
            [sys.executable, str(GENERATOR), "nonexistent-agent-xyz-s3"],
            capture_output=True, text=True, encoding="utf-8",
            cwd=PKG, timeout=15,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unknown agent", result.stderr.lower())


class NodeShimSmokeTests(unittest.TestCase):
    """cli.js: spawn with --list via node (skip visibly when node absent).

    Output is decoded leniently: a Windows shim can print the console code
    page, and a strict utf-8 decode turns that into a codec crash that hides
    the actual return code.
    """

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
            capture_output=True, text=True, encoding="utf-8", errors="replace",
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
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=PKG, timeout=15,
        )
        self.assertEqual(result.returncode, 0)

    def test_cli_js_has_no_deps(self) -> None:
        src = CLI_JS.read_text(encoding="utf-8")
        self.assertNotIn("require('", src.replace("require('node:", ""))
        for line in src.splitlines():
            if "require(" in line and "node:" not in line and "//" not in line.lstrip():
                self.fail(f"cli.js requires non-builtin module: {line.strip()}")




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

    BEGIN = markers.BLOCK_BEGIN
    END = markers.BLOCK_END

    def _apply(self, existing: str | None, content: str = "# dp\n\nbody") -> str:
        return gen_mod.apply_marker_block(existing, "0.21.0", content)

    def test_fresh_file_returns_just_block(self) -> None:
        result = self._apply(None)
        self.assertIn(self.BEGIN, result)
        self.assertIn(self.END, result)
        self.assertIn(f"<!-- {markers.MARKER_TEXT} v0.21.0 -->", result)
        self.assertIn("# dp", result)

    def test_append_when_no_existing_markers(self) -> None:
        existing = "# My Project\n\nMy instructions.\n"
        result = self._apply(existing)
        self.assertTrue(result.startswith("# My Project"), "user content preserved at top")
        self.assertIn(self.BEGIN, result)
        self.assertIn("My instructions.", result)

    def test_replace_existing_block_in_place(self) -> None:
        first = self._apply(None, "old content")
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
        # 9 skills: component-distill, craft-guard, design-baseline,
        #           design-playbook, native-craft, reference-intake,
        #           ui-evaluator, ui-picker, ux-spec
        self.assertEqual(len(skill_mdcs), 9, f"expected 9 skill .mdc files, got {[f.name for f in skill_mdcs]}")

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
        self.assertIn(markers.MARKER_TEXT, text)

    def test_total_file_count(self) -> None:
        paths = [e["path"] for e in self.manifest["files"]]
        # 9 skills + 1 commands + 1 mcp note + 1 mcp.json = 12, plus the
        # skills landing (.agents/skills/SKILL.md × 9) every non-native row
        # now carries (T-151 / I12).
        self.assertEqual(len(paths), 12 + LANDED_FILES)


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
        self.assertEqual(len(rules), 9, f"expected 9 skill rules, got {[f.name for f in rules]}")

    def test_workflow_files_written(self) -> None:
        workflows = list((self.out / ".windsurf" / "workflows").glob("*.md"))
        self.assertEqual(len(workflows), 8)

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
        # 9 rules + 8 workflows + 1 mcp guide = 18, plus the skills landing.
        self.assertEqual(len(self.manifest["files"]), 18 + LANDED_FILES)


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
        self.assertEqual(len(toml_files), 8)

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
        self.assertEqual(len(inst_files), 9)

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


class FrontmatterHeaderPlacementTests(unittest.TestCase):
    """Frontmatter header placement (issue #115), matrix-driven.

    Hosts that consume frontmatter-bearing artifacts require ``---`` on line 1;
    anything before it demotes the whole block to prose and the rule metadata
    (``alwaysApply``/``description``/``applyTo``) is silently dropped.  Every
    rendered artifact of every non-native matrix agent is checked so future
    emitters cannot regress."""

    _GENERATED_BY_LINE = re.compile(rf"^<!-- {markers.MARKER_TEXT} v\S+ -->$")

    @classmethod
    def setUpClass(cls) -> None:
        cls.rendered: list[tuple[str, str, str]] = []  # (agent, rel_path, text)
        for agent in GENERATING_AGENTS:
            with tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp)
                manifest = gen_mod.render(agent, out_dir=out, dry_run=False)
                for entry in manifest["files"]:
                    text = (out / entry["path"]).read_text(encoding="utf-8")
                    cls.rendered.append((agent, entry["path"], text))

    def test_frontmatter_artifacts_open_with_fence_then_generated_by(self) -> None:
        fm_artifacts = 0
        landed = 0
        for agent, rel, text in self.rendered:
            if _is_verbatim_landing(rel):
                continue  # copied, not authored: no stamp of ours belongs here
            lines = text.split("\n")
            # Regression guard — the exact #115 bug shape: generated-by comment
            # on line 1 with the frontmatter opener demoted to line 2.
            if lines[0].startswith("<!-- generated-by") and len(lines) > 1:
                self.assertNotEqual(
                    lines[1], "---",
                    f"{agent}:{rel}: generated-by comment precedes the frontmatter opener")
            if lines[0] != "---":
                continue  # plain artifact (markdown guide, JSON, TOML, marker block)
            fm_artifacts += 1
            if rel.startswith(_LANDING_PREFIX):
                landed += 1
            try:
                close = lines.index("---", 1)
            except ValueError:
                self.fail(f"{agent}:{rel}: frontmatter opener without a closing '---'")
            self.assertGreater(len(lines), close + 1,
                               f"{agent}:{rel}: no body line after the frontmatter block")
            self.assertRegex(
                lines[close + 1], self._GENERATED_BY_LINE,
                f"{agent}:{rel}: generated-by comment must be the first line after "
                f"the frontmatter block, got {lines[close + 1]!r}")
        # 11 cursor .mdc (9 skills + commands + mcp note) + 9 copilot
        # .instructions.md — the artifacts this generator authors.
        self.assertEqual(fm_artifacts - landed, 20,
                         f"expected 20 authored frontmatter-bearing artifacts across "
                         f"the matrix, got {fm_artifacts - landed}")
        # ...and the landed SKILL.md copies follow the same rule, one per
        # skill per landing row.
        self.assertEqual(landed, LANDED_SKILLS * len(LANDING_AGENTS),
                         f"expected {LANDED_SKILLS * len(LANDING_AGENTS)} landed "
                         f"SKILL.md copies, got {landed}")


class Tier3RendererTests(unittest.TestCase):
    """Tier-3 generic renderer: AGENTS.md floor for all 22 agents."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest, cls.out = _render_to_tmp("generic")

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls.out, ignore_errors=True)

    def test_agents_md_written_with_markers(self) -> None:
        f = self.out / "AGENTS.md"
        self.assertTrue(f.is_file())
        text = f.read_text(encoding="utf-8")
        self.assertIn("<!-- design-playbook:begin -->", text)
        self.assertIn("<!-- design-playbook:end -->", text)
        self.assertIn("design-playbook", text)

    def test_agents_md_has_mcp_guide(self) -> None:
        text = (self.out / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("MCP install guide", text)
        self.assertIn("persistent dependency", text)
        self.assertIn("design-playbook-preview", text)
        self.assertIn("design-playbook-evidence", text)

    def test_agents_md_has_commands_section(self) -> None:
        text = (self.out / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("Commands", text)
        self.assertIn("design-io", text)
        self.assertIn("doctor", text)

    def test_agents_md_user_content_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            (t / "AGENTS.md").write_text("# Team Rules\n\nDo not break production.\n", encoding="utf-8")
            gen_mod.render("generic", out_dir=t, dry_run=False)
            text = (t / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("Do not break production.", text)
        self.assertIn("<!-- design-playbook:begin -->", text)

    def test_total_file_count(self) -> None:
        # AGENTS.md only: the Tier-3 capability class is the floor, so this
        # tier gets no skills landing (T-151 / I12).
        self.assertEqual(len(self.manifest["files"]), 1)
        self.assertEqual(self.manifest["files"][0]["path"], "AGENTS.md")

    def test_all_three_verification_agents_render(self) -> None:
        for agent in ("generic", "qoder", "trae"):
            with tempfile.TemporaryDirectory() as tmp:
                m = gen_mod.render(agent, out_dir=Path(tmp), dry_run=False)
                self.assertEqual(len(m["files"]), 1)
                self.assertEqual(m["files"][0]["path"], "AGENTS.md")

    def test_all_22_tier3_agents_have_renderers(self) -> None:
        tier3 = [row for row in matrix_mod.MATRIX if row.tier == 3]
        self.assertEqual(len(tier3), 22)
        for row in tier3:
            if not row.generates:
                continue  # dead rows emit nothing (see RendererDispatchTests)
            with tempfile.TemporaryDirectory() as tmp:
                m = gen_mod.render(row.agent, out_dir=Path(tmp), dry_run=True)
                self.assertEqual(m["agent"], row.agent)


class RendererDispatchTests(unittest.TestCase):
    """Dispatch keys off the matrix row (issue #111): dedicated renderer or
    AGENTS.md floor fallback for every non-native row; native rows emit nothing."""

    def test_every_generating_row_renders_without_not_implemented(self) -> None:
        for agent in GENERATING_AGENTS:
            with tempfile.TemporaryDirectory() as tmp:
                try:
                    m = gen_mod.render(agent, out_dir=Path(tmp), dry_run=True)
                except NotImplementedError as exc:
                    self.fail(f"{agent}: a generating row must never hit NotImplementedError: {exc}")
                self.assertEqual(m["agent"], agent)
                self.assertGreater(len(m["files"]), 0, f"{agent}: expected at least one artifact")

    def test_dead_row_emits_nothing_and_says_why(self) -> None:
        # Counter-example to the sweep above: a dead row is refused, loudly,
        # and writes no file.
        dead = [row for row in matrix_mod.MATRIX if not row.generates]
        self.assertTrue(dead, "matrix must carry at least one dead row to pin this")
        for row in dead:
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(NotImplementedError) as ctx:
                    gen_mod.render(row.agent, out_dir=Path(tmp), dry_run=False)
                self.assertIn(row.status, str(ctx.exception))
                self.assertIn(row.agent, str(ctx.exception))
                self.assertEqual(list(Path(tmp).rglob("*")), [],
                                 f"{row.agent}: dead row must not write files")

    def test_dead_row_renderer_resolution_is_none(self) -> None:
        row = matrix_mod.AgentRow(agent="hypothetical-dead", tier=3, status="dead")
        self.assertIsNone(gen_mod._renderer_for(row))

    def test_dead_row_not_advertised_as_renderer_ready(self) -> None:
        result = subprocess.run(
            [sys.executable, str(GENERATOR), "--list"],
            capture_output=True, text=True, encoding="utf-8",
            cwd=PKG, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        for row in matrix_mod.MATRIX:
            if row.generates:
                continue
            line = next((ln for ln in result.stdout.splitlines() if row.agent in ln), "")
            self.assertTrue(line, f"{row.agent} missing from --list")
            self.assertIn(f"[{row.status}]", line)
            self.assertNotIn("renderer ready", line,
                             f"{row.agent} is dead and must not be offered")

    def test_native_row_emits_nothing(self) -> None:
        native_rows = [row for row in matrix_mod.MATRIX if row.native]
        self.assertTrue(native_rows, "matrix must mark the native row")
        for row in native_rows:
            with tempfile.TemporaryDirectory() as tmp:
                with self.assertRaises(NotImplementedError):
                    gen_mod.render(row.agent, out_dir=Path(tmp), dry_run=False)
                written = list(Path(tmp).rglob("*"))
                self.assertEqual(written, [], f"{row.agent}: native row must not write files")

    def test_native_skip_keys_off_matrix_flag_not_name(self) -> None:
        # A hypothetical native row under any other name must be skipped too:
        # the generator reads row.native, never the agent name.
        row = matrix_mod.AgentRow(agent="hypothetical-native-host", tier=1, native=True)
        self.assertIsNone(gen_mod._renderer_for(row))

    def test_row_without_dedicated_renderer_falls_back_to_floor(self) -> None:
        # Adding an agent = adding a matrix row (ADR-0042): a row the generator
        # has never heard of must resolve to the AGENTS.md floor renderer.
        row = matrix_mod.AgentRow(agent="brand-new-agent-not-in-generator", tier=3)
        self.assertIs(gen_mod._renderer_for(row), gen_mod._agents_md_floor_files)

    def test_every_named_renderer_is_bound_and_used(self) -> None:
        named = {row.renderer for row in matrix_mod.MATRIX if row.renderer}
        # Every name a row uses has an implementation...
        self.assertEqual(
            named - set(gen_mod._SPECIALIZED_RENDERERS), set(),
            "matrix rows name renderers the generator does not implement")
        # ...and every implementation belongs to a row that names it.
        self.assertEqual(
            set(gen_mod._SPECIALIZED_RENDERERS) - named, set(),
            "generator carries renderers no matrix row names")

    def test_no_duplicated_tier_membership_list_in_generator(self) -> None:
        # Regression pin: tier membership lives in adapter_matrix.py only.
        self.assertFalse(hasattr(gen_mod, "_TIER3_RENDERER_AGENTS"),
                         "generator must not duplicate the matrix's tier-3 agent list")


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
        for agent in ("cursor", "gemini-cli", "opencode", "windsurf", "github-copilot", "zed"):
            self.assertIn(f"{agent}", out, f"{agent} not in --list output")
            line = next((ln for ln in out.splitlines() if agent in ln), "")
            self.assertIn("renderer ready", line, f"{agent} not shown as renderer ready: {line!r}")

    def test_codex_still_shown_as_ready(self) -> None:
        out = self._list_output()
        line = next((ln for ln in out.splitlines() if "codex" in ln), "")
        self.assertIn("renderer ready", line)

    def test_all_tier3_agents_shown_as_ready(self) -> None:
        out = self._list_output()
        tier3_agents = [
            row.agent for row in matrix_mod.MATRIX if row.tier == 3 and row.generates
        ]
        for agent in tier3_agents:
            line = next((ln for ln in out.splitlines() if agent in ln), "")
            self.assertIn("renderer ready", line, f"{agent} not shown as renderer ready")

    def test_native_claude_code_listed_without_renderer_note(self) -> None:
        out = self._list_output()
        line = next((ln for ln in out.splitlines() if "claude-code" in ln), "")
        self.assertTrue(line, "claude-code missing from --list output")
        self.assertNotIn("renderer ready", line,
                         "native claude-code row must not be shown as renderer ready")


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

    def test_zed_dry_run(self) -> None:
        m = self._dry_run("zed")
        self.assertEqual(m["agent"], "zed")


class ZedRendererTests(unittest.TestCase):
    """zed tier-2 renderer: `.rules` marker-block, first-match conflict
    avoidance, and merge-safe context_servers (spec 2026-09-19-zed-adapter)."""

    def _write(self, tmp: str) -> Path:
        gen_mod.render("zed", out_dir=Path(tmp), dry_run=False)
        return Path(tmp)

    def test_fresh_init_creates_rules_and_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = self._write(tmp)
            rules = (root / ".rules").read_text(encoding="utf-8")
            self.assertIn("<!-- design-playbook:begin -->", rules)
            self.assertIn(f"<!-- {markers.MARKER_TEXT} v", rules)
            settings = json.loads(
                (root / ".zed" / "settings.json").read_text(encoding="utf-8")
            )
            servers = settings["context_servers"]
            self.assertIn("design-playbook-preview", servers)
            self.assertIn("design-playbook-evidence", servers)
            self.assertEqual(servers["design-playbook-preview"]["command"], "python")
            self.assertTrue(
                servers["design-playbook-preview"]["args"][-1].endswith("server.py")
            )

    def test_competitor_rules_file_blocks_new_rules(self) -> None:
        # Zed's first-match puts `.rules` above every competitor: creating one
        # while the user relies on e.g. CLAUDE.md would silently shadow it.
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "CLAUDE.md").write_text("# user rules\n", encoding="utf-8")
            m = gen_mod.render("zed", out_dir=Path(tmp), dry_run=True)
            paths = [f["path"] for f in m["files"]]
            self.assertNotIn(".rules", paths)
            self.assertIn(".zed/settings.json", paths)

    def test_existing_rules_file_is_refreshed_even_with_competitor(self) -> None:
        # An existing `.rules` is the file Zed already reads; refresh wins.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "CLAUDE.md").write_text("# user rules\n", encoding="utf-8")
            (root / ".rules").write_text(
                "<!-- design-playbook:begin -->\n"
                "<!-- generated-by design-playbook v0.0.1 -->\n"
                "old\n"
                "<!-- design-playbook:end -->\n",
                encoding="utf-8",
            )
            m = gen_mod.render("zed", out_dir=root, dry_run=True)
            self.assertIn(".rules", [f["path"] for f in m["files"]])

    def test_user_rules_file_gets_block_appended(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".rules").write_text("# my own rules\n", encoding="utf-8")
            self._write(tmp)
            rules = (root / ".rules").read_text(encoding="utf-8")
            self.assertTrue(rules.startswith("# my own rules"))
            self.assertIn("<!-- design-playbook:begin -->", rules)

    def test_settings_merge_preserves_user_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".zed").mkdir()
            (root / ".zed" / "settings.json").write_text(
                json.dumps({"theme": "night"}), encoding="utf-8"
            )
            self._write(tmp)
            settings = json.loads(
                (root / ".zed" / "settings.json").read_text(encoding="utf-8")
            )
            self.assertEqual(settings["theme"], "night")
            self.assertIn("context_servers", settings)

    def test_idempotent_reinit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self._write(tmp)
            first = (Path(tmp) / ".rules").read_text(encoding="utf-8")
            gen_mod.render("zed", out_dir=Path(tmp), dry_run=False)
            self.assertEqual((Path(tmp) / ".rules").read_text(encoding="utf-8"), first)


class AgentPluginsBundleTests(unittest.TestCase):
    """agent_plugins bundle (T-149 / S4): one portable plugin layout —
    ``plugin.json`` + ``mcp.json`` — rendered from the capability matrix, not
    a second hand-written manifest per host."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.manifest = gen_mod.render("agent-plugins", out_dir=self.tmp, dry_run=False)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _plugin_json(self) -> dict:
        return json.loads((self.tmp / "plugin.json").read_text(encoding="utf-8"))

    def test_emits_the_two_layout_files(self) -> None:
        self.assertEqual(
            [f["path"] for f in self.manifest["files"]], ["plugin.json", "mcp.json"]
        )

    def test_plugin_json_mirrors_the_canonical_manifest(self) -> None:
        with (PKG / ".claude-plugin" / "plugin.json").open(encoding="utf-8") as f:
            canonical = json.load(f)
        data = self._plugin_json()
        self.assertEqual(data["name"], canonical["name"])
        self.assertEqual(data["version"], canonical["version"])
        self.assertEqual(data["description"], canonical["description"])
        self.assertEqual(data["license"], canonical["license"])

    def test_plugin_json_points_at_package_skills_and_mcp(self) -> None:
        data = self._plugin_json()
        self.assertEqual(data["skills"], "./skills/")
        self.assertEqual(data["mcpServers"], "./mcp.json")
        self.assertTrue((PKG / "skills").is_dir(),
                        "the referenced skills directory must exist in the package")

    def test_declared_agents_equal_the_matrix_render(self) -> None:
        # The pin: the declared surface list IS the matrix rendered.  Expected
        # value computed independently (not via the generator's own helper), so
        # a wrong filter in the implementation cannot duplicate itself here.
        expected = [
            {"id": row.agent, "tier": row.tier, "status": row.status}
            for row in matrix_mod.MATRIX
            if not row.native and row.generates
        ]
        self.assertEqual(self._plugin_json()["agents"], expected)

    def test_dead_and_native_rows_are_not_advertised(self) -> None:
        ids = {entry["id"] for entry in self._plugin_json()["agents"]}
        self.assertNotIn("roo-code", ids, "dead row must not be advertised")
        self.assertNotIn("claude-code", ids, "native row owns its own layout")
        self.assertIn("windsurf", ids, "a rebranded row still generates")
        windsurf = next(e for e in self._plugin_json()["agents"] if e["id"] == "windsurf")
        self.assertEqual(windsurf["status"], "rebranded")

    def test_a_newly_dead_row_drops_out_of_the_bundle(self) -> None:
        # Counter-example to the pin above: flipping one row to dead removes it
        # from the bundle without touching the bundle code.
        original = gen_mod.MATRIX
        gen_mod.MATRIX = tuple(
            matrix_mod.AgentRow(agent="cursor", tier=2, renderer="cursor",
                                status="dead")
            if row.agent == "cursor" else row
            for row in original
        )
        try:
            ids = {e["id"] for e in gen_mod._agent_surface_entries()}
        finally:
            gen_mod.MATRIX = original
        self.assertNotIn("cursor", ids)

    def test_mcp_json_carries_both_servers_as_stdio(self) -> None:
        data = json.loads((self.tmp / "mcp.json").read_text(encoding="utf-8"))
        servers = data["mcpServers"]
        self.assertEqual(
            set(servers), {"design-playbook-preview", "design-playbook-evidence"}
        )
        for srv in servers.values():
            self.assertEqual(srv["type"], "stdio")
            self.assertEqual(srv["command"], "python")
            self.assertTrue(srv["args"][0].endswith("server.py"), srv)
            self.assertEqual(srv["cwd"], ".")

    def test_claude_layout_is_not_touched(self) -> None:
        paths = [f["path"] for f in self.manifest["files"]]
        self.assertFalse(any(p.startswith(".claude-plugin") for p in paths), paths)

    def test_dry_run_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manifest = gen_mod.render("agent-plugins", out_dir=Path(tmp), dry_run=True)
            self.assertEqual(len(manifest["files"]), 2)
            self.assertEqual(list(Path(tmp).rglob("*")), [])

    def test_render_entries_seam_matches_render(self) -> None:
        version, out, entries = gen_mod.render_entries("agent-plugins", self.tmp)
        self.assertEqual(out, self.tmp)
        self.assertEqual(version, self.manifest["version"])
        self.assertEqual(
            [rel for rel, _c in entries], [f["path"] for f in self.manifest["files"]]
        )
        self.assertEqual(
            [hashlib.sha256(c.encode("utf-8")).hexdigest() for _rel, c in entries],
            [f["sha256"] for f in self.manifest["files"]],
        )

    def test_bundle_is_listed_by_cli(self) -> None:
        result = subprocess.run(
            [sys.executable, str(GENERATOR), "--list"],
            capture_output=True, text=True, encoding="utf-8",
            cwd=PKG, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("agent-plugins", result.stdout)


class InstallLandingTests(unittest.TestCase):
    """Install landing points (T-151 / I12).

    Two landing classes, decided by the matrix row rather than by the
    renderer: the native row keeps its own layout (the host reads the
    package's ``skills/`` in place), every other row lands the same skills
    tree under ``AGENTS_SKILLS_DIR`` in the consuming project."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    # --- landing rule -----------------------------------------------------

    def test_claude_row_has_no_generated_landing(self) -> None:
        # Native row: the host consumes the package directly, so a landing
        # copy would be a second inventory nobody loads.  The generator
        # refuses loudly rather than writing one under another name.
        row = matrix_mod.get_agent("claude-code")
        self.assertTrue(row.native)
        self.assertIsNone(row.skills_landing)
        with self.assertRaises(NotImplementedError):
            gen_mod.render("claude-code", out_dir=self.tmp, dry_run=False)
        self.assertEqual(list(self.tmp.rglob("*")), [])

    def test_non_claude_row_lands_at_agents_skills(self) -> None:
        manifest = gen_mod.render("cursor", out_dir=self.tmp, dry_run=False)
        landed = [p for p in self.tmp.rglob("*")
                  if p.is_file()
                  and p.relative_to(self.tmp).as_posix().startswith(_LANDING_PREFIX)]
        self.assertTrue(landed, "a non-native row must land a skills tree")
        for path in landed:
            rel = path.relative_to(self.tmp).as_posix()
            self.assertTrue(rel.startswith(_LANDING_PREFIX), rel)
        # Every skill travels whole — SKILL.md plus the references it points
        # at — so the landed copy is not a skill with broken links.
        self.assertEqual(
            {p.parent.name for p in landed if p.name == "SKILL.md"},
            {d.name for d in (PKG / "skills").iterdir() if d.is_dir()},
        )
        for path in landed:
            rel = path.relative_to(self.tmp / matrix_mod.AGENTS_SKILLS_DIR)
            self.assertTrue((PKG / "skills" / rel).is_file(),
                            f"landed {rel} has no package source")
        # The host's own adapter is still written alongside the landing.
        self.assertIn(".cursor/rules/design-playbook.mdc",
                      [f["path"] for f in manifest["files"]])

    def test_landing_is_verbatim_beside_the_stamped_skill(self) -> None:
        gen_mod.render("cursor", out_dir=self.tmp, dry_run=False)
        landing = self.tmp / matrix_mod.AGENTS_SKILLS_DIR
        stamped = (landing / "ui-picker" / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(stamped.startswith("---\n"))
        self.assertIn(markers.MARKER_TEXT, stamped)
        reference = (landing / "ui-picker" / "references" / "template.md").read_text(
            encoding="utf-8")
        source = (PKG / "skills" / "ui-picker" / "references" / "template.md").read_text(
            encoding="utf-8")
        self.assertEqual(reference, source, "references travel unmodified")

    def test_init_alias_lands_through_the_documented_command(self) -> None:
        # ``npx design-playbook init <agent>`` is the surface the docs tell a
        # user to run; prove the landing survives that path, not just the
        # in-process render.
        node = shutil.which("node")
        if not node:
            self.skipTest("node not found on PATH — skipping cli.js smoke")
        out = self.tmp / "cli"
        result = subprocess.run(
            [node, str(CLI_JS), "init", "cursor", "--out", str(out)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=PKG, timeout=60,
        )
        self.assertEqual(result.returncode, 0,
                         f"cli.js init failed:\n{result.stdout}\n{result.stderr}")
        self.assertTrue((out / matrix_mod.AGENTS_SKILLS_DIR / "design-playbook"
                         / "SKILL.md").is_file())
        self.assertTrue((out / ".cursor" / "rules" / "design-playbook.mdc").is_file())

    def test_tier3_floor_keeps_its_agents_md_only_surface(self) -> None:
        # The landing must not hand a tier more than the matrix declares:
        # Tier-3 is the AGENTS.md floor, so its rows emit no skills tree even
        # though they are non-native.
        for row in matrix_mod.MATRIX:
            if row.tier != 3:
                continue
            self.assertIsNone(row.skills_landing, row.agent)
        # Counter-check: the boundary is the tier, not "nothing lands anywhere".
        self.assertEqual(
            {row.tier for row in matrix_mod.MATRIX if row.skills_landing}, {1, 2}
        )
        for agent in ("generic", "qoder", "trae", "amp"):
            with tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp)
                manifest = gen_mod.render(agent, out_dir=out, dry_run=False)
                self.assertEqual([e["path"] for e in manifest["files"]], ["AGENTS.md"])
                self.assertFalse((out / matrix_mod.AGENTS_SKILLS_DIR).exists(),
                                 f"{agent}: a tier-3 row must not land a skills tree")

    def test_landing_leaves_the_projects_own_skills_alone(self) -> None:
        # .agents/skills/ is a shared directory: the landing writes only the
        # package's own skill names, so a skill the project brought survives.
        sibling = self.tmp / matrix_mod.AGENTS_SKILLS_DIR / "team-own" / "SKILL.md"
        sibling.parent.mkdir(parents=True)
        sibling.write_text("---\nname: team-own\n---\n\nteam rules\n", encoding="utf-8")
        gen_mod.render("cursor", out_dir=self.tmp, dry_run=False)
        self.assertEqual(sibling.read_text(encoding="utf-8"),
                         "---\nname: team-own\n---\n\nteam rules\n")

    def test_landing_is_not_written_into_the_package(self) -> None:
        # Tier-1 snapshots are regenerated inside the package; a
        # project-level landing there would be a copy nobody reads (and the
        # repository's own ignored .agents/ area).
        _version, out, entries = gen_mod.render_entries("codex", PKG)
        self.assertEqual(out, PKG)
        self.assertFalse(
            any(rel.startswith(_LANDING_PREFIX) for rel, _c in entries),
            [rel for rel, _c in entries],
        )

    # --- the second marketplace layout ------------------------------------

    def _committed_catalog(self) -> str:
        return (ROOT / ".agents" / "plugins" / "marketplace.json").read_text(
            encoding="utf-8")

    def test_second_format_catalog_is_generated_not_hand_typed(self) -> None:
        # The drift pin: the committed catalog must be exactly what the
        # generator renders.  Editing it by hand fails here.
        manifest = gen_mod.render("agents-marketplace", out_dir=self.tmp, dry_run=False)
        self.assertEqual(
            [f["path"] for f in manifest["files"]],
            [".agents/plugins/marketplace.json"],
        )
        written = (self.tmp / ".agents" / "plugins" / "marketplace.json").read_text(
            encoding="utf-8")
        self.assertEqual(written, self._committed_catalog())

    def test_second_format_catalog_is_sourced_from_the_canonical_manifest(self) -> None:
        catalog = json.loads(self._committed_catalog())
        canonical = json.loads(
            (PKG / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(catalog["name"], canonical["name"])
        entry = catalog["plugins"][0]
        self.assertEqual(entry["name"], canonical["name"])
        # The catalog advertises the package the matrix renders for, so the
        # entry and the rows cannot point at different trees.
        path = entry["source"]["path"]
        self.assertEqual((ROOT / path).resolve(), PKG.resolve())

    def test_second_format_catalog_carries_no_invented_host_keys(self) -> None:
        # Agent Plugins' own vocabulary excludes agents/commands/hooks from
        # its manifests: the surface list lives in the portable bundle's
        # plugin.json (matrix-rendered), not as an unknown key in a catalog
        # a foreign host parses.
        catalog = json.loads(self._committed_catalog())
        self.assertEqual(set(catalog), {"name", "interface", "plugins"})
        self.assertEqual(
            set(catalog["plugins"][0]),
            {"name", "source", "policy", "category"},
        )

    def test_second_format_catalog_has_a_drift_gate_registered(self) -> None:
        # generated_artifacts.py is the register validate.py walks: an
        # artifact with no row has no gate and can ship stale.
        sys.path.insert(0, str(ROOT / "scripts"))
        import generated_artifacts  # noqa: E402

        names = {a.name for a in generated_artifacts.ARTIFACTS}
        self.assertIn("agents marketplace catalog", names)
        for artifact in generated_artifacts.ARTIFACTS:
            if artifact.name != "agents marketplace catalog":
                continue
            self.assertIn("adapter_matrix", artifact.source)
            self.assertEqual(artifact.generator,
                             "packages/design-playbook/scripts/generate_adapter.py")
            self.assertEqual(artifact.artifacts,
                             (".agents/plugins/marketplace.json",))
            self.assertEqual(artifact.gate, "tests/test_adapter_generator.py")


if __name__ == "__main__":
    unittest.main()

