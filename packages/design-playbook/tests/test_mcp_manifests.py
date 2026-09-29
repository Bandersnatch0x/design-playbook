#!/usr/bin/env python3
"""Manifest-level regression for the MCP server config files.

Issue 05 (Codex RUN_ROOT): a static ``DESIGN_PLAYBOOK_RUN_ROOT="."`` in either
manifest pins evidence capture to the plugin install location, so Codex
installs wrote artifacts into the read-only plugin cache instead of the host
workspace. The fix is to drop the static env var from both manifests and rely
on ``server.py _run_root()`` env->cwd fallback (host controls cwd; Codex keeps
``cwd: "."`` and Claude launches via ``${CLAUDE_PLUGIN_ROOT}``).

Issue 09 amended (directory schema): the run_root passthrough is expressed with
each host's *real* env channel, not one shared shape. Codex has no env
interpolation, so it uses the ``env_vars`` name-passthrough (host sets the value
before launch). Claude Code's ``.mcp.json`` schema has no ``env_vars`` key -- it
uses a standard ``env`` object with ``${VAR:-}`` interpolation -- and the
directory submission validator checks ``.mcp.json`` against that schema, so the
Claude side must not carry the non-standard ``env_vars`` key. Both forms keep the
Issue 05 invariant: no *static* run root is pinned (``${VAR:-}`` expands to "" ->
cwd fallback when unset).

These tests pin the post-fix invariant so a static var cannot silently come
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
        # Issue 05 invariant: a value may only *pass through* the host's
        # run root, never pin a static one. An ``env`` entry is allowed when
        # its value is a ``${...}`` interpolation (empty -> cwd fallback);
        # a literal like "." or a fixed path is the regression this guards.
        env = self._evidence().get("env") or {}
        value = env.get(RUN_ROOT_ENV)
        assert value is None or "${" in str(value), (
            f"{self.manifest_path.name}: {RUN_ROOT_ENV} in env must be a "
            f"${{...}} passthrough, not a static value (got {value!r}); "
            "server._run_root() falls back to process cwd when unset"
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

    def test_evidence_forwards_run_root_via_env_interpolation(self) -> None:
        # Issue 09 amended (ADR-0009): Claude uses its host's real env channel.
        # Claude Code's .mcp.json schema has no ``env_vars`` key; it forwards a
        # host variable with a standard ``env`` object + ``${VAR:-}``
        # interpolation (resolved from Claude Code's own environment, so it also
        # survives the sanitized child env on Windows). The directory submission
        # validator checks .mcp.json against that schema, so the non-standard
        # ``env_vars`` key must not appear here (it stays on the Codex side,
        # whose loader has no interpolation).
        evidence = self._evidence()
        self.assertNotIn(
            "env_vars",
            evidence,
            "Claude manifest must not use the non-standard env_vars key; the "
            "directory .mcp.json schema is env-object only (ADR-0009 amended)",
        )
        env = evidence.get("env") or {}
        value = str(env.get(RUN_ROOT_ENV, ""))
        self.assertTrue(
            RUN_ROOT_ENV in value and "${" in value,
            "Claude manifest must forward DESIGN_PLAYBOOK_RUN_ROOT via a "
            f"${{{RUN_ROOT_ENV}:-}} env interpolation (got {value!r})",
        )


if __name__ == "__main__":
    unittest.main()
