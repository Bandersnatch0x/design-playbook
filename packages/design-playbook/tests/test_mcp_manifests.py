#!/usr/bin/env python3
"""Manifest-level regression for the MCP server config files.

Issue 05 (Codex RUN_ROOT): a static ``DESIGN_PLAYBOOK_RUN_ROOT="."`` in either
manifest pins evidence capture to the plugin install location, so Codex
installs wrote artifacts into the read-only plugin cache instead of the host
workspace. The fix is to drop the static env var from both manifests and rely
on ``server.py _run_root()`` env->cwd fallback (host controls cwd; Codex keeps
``cwd: "."`` and Claude launches via ``${CLAUDE_PLUGIN_ROOT}``).

These tests pin the post-fix invariant so the static var cannot silently come
back. They intentionally do not exercise ``server.py`` (owned by the evidence
domain).
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent
CODEX_MANIFEST = PACKAGE / ".codex-plugin" / "mcp.json"
CLAUDE_MANIFEST = PACKAGE / ".mcp.json"

EVIDENCE_SERVER = "design-playbook-evidence"
RUN_ROOT_ENV = "DESIGN_PLAYBOOK_RUN_ROOT"


class _ManifestMixin:
    """Shared helpers — subclasses declare which manifest to assert against.

    Not a ``unittest.TestCase`` so pytest does not collect it directly;
    concrete test classes bring ``TestCase`` in themselves.
    """

    manifest_path: Path

    def setUp(self) -> None:  # type: ignore[override]
        assert self.manifest_path.is_file(), f"{self.manifest_path} must exist"
        self.doc: dict = json.loads(
            self.manifest_path.read_text(encoding="utf-8")
        )

    def _evidence(self) -> dict:
        servers = self.doc.get("mcpServers", {})
        assert EVIDENCE_SERVER in servers, (
            f"{self.manifest_path.name}: {EVIDENCE_SERVER} entry missing"
        )
        return servers[EVIDENCE_SERVER]

    def test_parses_as_valid_json(self) -> None:
        # setUp already parses; re-assert the top-level shape so a future edit
        # that breaks the envelope (e.g. stray trailing comma) surfaces here.
        assert "mcpServers" in self.doc
        assert isinstance(self.doc["mcpServers"], dict)

    def test_evidence_has_no_static_run_root(self) -> None:
        env = self._evidence().get("env") or {}
        assert RUN_ROOT_ENV not in env, (
            f"{self.manifest_path.name}: static {RUN_ROOT_ENV} must be "
            "removed; server._run_root() falls back to process cwd when unset"
        )


class CodexManifestTest(_ManifestMixin, unittest.TestCase):
    manifest_path = CODEX_MANIFEST

    def test_keeps_relative_cwd(self) -> None:
        # Issue 09 (env_vars passthrough): cwd stays "." so the loader anchors
        # it to plugin_root, which is what lets the relative args resolve the
        # server script (server.py self-locates via __file__ for its imports,
        # so cwd is single-duty = script location, not run_root). run_root now
        # comes from env_vars passthrough, not cwd.
        evidence = self._evidence()
        self.assertEqual(
            evidence.get("cwd"),
            ".",
            "Codex manifest must keep cwd='.' (anchored to plugin_root by the "
            "loader) so the relative args resolve the server script",
        )

    def test_evidence_passes_through_run_root_env_var(self) -> None:
        # Issue 09: codex has no workspace variable and no env interpolation,
        # so the only host-trusted channel for run_root is env_vars (name
        # passthrough). The host sets DESIGN_PLAYBOOK_RUN_ROOT before launching
        # codex; this entry forwards it to the evidence server process.
        evidence = self._evidence()
        env_vars = evidence.get("env_vars") or []
        self.assertIn(
            RUN_ROOT_ENV,
            env_vars,
            "Codex manifest must list DESIGN_PLAYBOOK_RUN_ROOT in env_vars so "
            "the host-set value is forwarded to the evidence server "
            "(codex has no workspace variable / env interpolation)",
        )


class ClaudeManifestTest(_ManifestMixin, unittest.TestCase):
    manifest_path = CLAUDE_MANIFEST

    def test_launches_via_plugin_root_variable(self) -> None:
        # Claude side has no cwd; it launches the server via the absolute
        # ${CLAUDE_PLUGIN_ROOT} arg. The structural difference vs Codex
        # (variable vs static ".") is the documented root cause of issue 05.
        evidence = self._evidence()
        self.assertNotIn(
            "cwd",
            evidence,
            "Claude manifest must not pin cwd; host runtime resolves "
            "${CLAUDE_PLUGIN_ROOT}",
        )
        args = evidence.get("args") or []
        self.assertTrue(
            any("${CLAUDE_PLUGIN_ROOT}" in str(a) for a in args),
            "Claude manifest must reference ${CLAUDE_PLUGIN_ROOT} in args",
        )

    def test_evidence_passes_through_run_root_env_var(self) -> None:
        # Issue 09 (ADR-0009 symmetry): Claude side mirrors the Codex env_vars
        # passthrough. Behavior is unchanged when unset (falls back to
        # Path.cwd() = host project), but the symmetric declaration keeps the
        # run_root mechanism consistent across both manifests.
        evidence = self._evidence()
        env_vars = evidence.get("env_vars") or []
        self.assertIn(
            RUN_ROOT_ENV,
            env_vars,
            "Claude manifest must mirror the Codex env_vars passthrough for "
            "DESIGN_PLAYBOOK_RUN_ROOT (ADR-0009 run_root mechanism symmetry)",
        )


if __name__ == "__main__":
    unittest.main()
