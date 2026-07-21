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
        # Codex has no workspace variable, so cwd stays as "." — the host
        # installer is expected to anchor it to the host workspace. Removing
        # the static RUN_ROOT relies on this cwd flowing into _run_root().
        evidence = self._evidence()
        self.assertEqual(
            evidence.get("cwd"),
            ".",
            "Codex manifest must keep cwd='.' so _run_root() cwd-fallback "
            "resolves to the host workspace, not the plugin cache",
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


if __name__ == "__main__":
    unittest.main()
