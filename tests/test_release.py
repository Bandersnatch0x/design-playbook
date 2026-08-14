#!/usr/bin/env python3
"""Black-box regression tests for the release gate.

The tests are pinned to the *current* version read from plugin.json (rather
than a hardcoded literal) so they survive every version bump without
bit-rotting the tag/release-notes assertions.
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
RELEASE = ROOT / "scripts" / "release.py"
sys.path.insert(0, str(ROOT / "scripts"))

from _checks import release_group_errors  # noqa: E402


def _current_version() -> str:
    """Read the shipped plugin version so tests track release.py's own source."""
    plugin_json = ROOT / "packages" / "design-playbook" / ".claude-plugin" / "plugin.json"
    return json.loads(plugin_json.read_text(encoding="utf-8"))["version"]


CURRENT_VERSION = _current_version()
CURRENT_TAG = f"v{CURRENT_VERSION}"
CURRENT_NOTES_REL = f"docs/releases/{CURRENT_TAG}.md"


def _run(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*args], cwd=cwd, capture_output=True, text=True, check=False,
    )


class ReleaseGroupPolicyTests(unittest.TestCase):
    def test_release_group_manifest_contract(self) -> None:
        main = {"name": "design-playbook", "version": "1.2.3"}
        dsh = {
            "name": "dsh-design-playbook",
            "version": "1.2.3",
            "dependencies": {"design-playbook": "^1.2.3"},
        }

        invalid_cases = (
            ([], dsh, "design-playbook package.json must contain a JSON object"),
            ({}, dsh, "design-playbook version None is not stable semver"),
            (main, {"version": "1.2"}, "dsh-design-playbook version '1.2' is not stable semver"),
            (
                main,
                {"version": "1.2.3"},
                "dsh-design-playbook dependency on design-playbook None; expected '^1.2.3'",
            ),
            (
                main,
                {"version": "1.2.4", "dependencies": {"design-playbook": "^1.2.3"}},
                "dsh-design-playbook version '1.2.4' does not match design-playbook version '1.2.3'",
            ),
        )
        for main_manifest, dsh_manifest, expected in invalid_cases:
            with self.subTest(expected=expected):
                self.assertIn(
                    expected,
                    release_group_errors(main_manifest, dsh_manifest),
                )

        self.assertEqual(release_group_errors(main, dsh), ())


class ReleaseGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        shutil.copytree(ROOT / "scripts", self.root / "scripts")
        shutil.copytree(
            ROOT / "packages" / "design-playbook",
            self.root / "packages" / "design-playbook",
        )
        shutil.copytree(
            ROOT / "packages" / "dsh-design-playbook",
            self.root / "packages" / "dsh-design-playbook",
        )
        shutil.copytree(ROOT / ".claude-plugin", self.root / ".claude-plugin")
        shutil.copy2(ROOT / "README.md", self.root / "README.md")
        shutil.copy2(ROOT / "README-zh.md", self.root / "README-zh.md")
        (self.root / "docs" / "releases").mkdir(parents=True)
        # Copy the release-notes file for the current version so version-gate
        # tests find it; test_release_notes_for_version_are_required deletes
        # it explicitly to force the miss.
        shutil.copy2(
            ROOT / CURRENT_NOTES_REL,
            self.root / CURRENT_NOTES_REL,
        )
        _run("git", "init", cwd=self.root)
        _run("git", "config", "user.email", "release-test@example.com", cwd=self.root)
        _run("git", "config", "user.name", "Release Test", cwd=self.root)
        _run("git", "add", ".", cwd=self.root)
        committed = _run("git", "commit", "-m", "fixture", cwd=self.root)
        self.assertEqual(committed.returncode, 0, committed.stderr)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def release(self, *args: str) -> subprocess.CompletedProcess[str]:
        return _run(sys.executable, str(self.root / "scripts" / "release.py"), *args, cwd=self.root)

    def test_untracked_file_blocks_release_by_default(self) -> None:
        (self.root / "untracked.txt").write_text("not released\n", encoding="utf-8")

        result = self.release("--checks", "tree,tag")

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("untracked.txt", result.stdout)
        self.assertIn("working tree has uncommitted changes", result.stdout)

    def test_existing_tag_at_head_is_idempotent(self) -> None:
        tagged = _run("git", "tag", CURRENT_TAG, cwd=self.root)
        self.assertEqual(tagged.returncode, 0, tagged.stderr)

        result = self.release("--checks", "tree,tag")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"tag {CURRENT_TAG} already points at HEAD", result.stdout)

    def test_apply_refuses_to_tag_when_a_gate_failed(self) -> None:
        (self.root / "untracked.txt").write_text("not released\n", encoding="utf-8")

        result = self.release("--checks", "tree,tag", "--apply")

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("refusing to create tag", result.stdout)
        tags = _run("git", "tag", "-l", CURRENT_TAG, cwd=self.root)
        self.assertEqual(
            tags.stdout.strip(), "",
            "tag must not be created when an earlier gate failed")

    def test_release_notes_for_version_are_required(self) -> None:
        (self.root / CURRENT_NOTES_REL).unlink()

        result = self.release("--checks", "version")

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(CURRENT_NOTES_REL, result.stdout)

    def test_fixture_includes_codex_plugin_manifest(self) -> None:
        # Regression guard for issue 07: the release fixture must carry the
        # Codex dual-publish manifest so check_version can police drift
        # between Claude and Codex plugin.json (ADR-0009).
        codex_plugin = (
            self.root / "packages" / "design-playbook" / ".codex-plugin" / "plugin.json"
        )
        codex_mcp = (
            self.root / "packages" / "design-playbook" / ".codex-plugin" / "mcp.json"
        )
        self.assertTrue(codex_plugin.is_file(), "fixture missing .codex-plugin/plugin.json")
        self.assertTrue(codex_mcp.is_file(), "fixture missing .codex-plugin/mcp.json")

    def test_codex_plugin_json_version_must_match_claude(self) -> None:
        # Issue 07 acceptance: bump漏改 .codex-plugin/plugin.json -> release FAIL.
        codex_plugin = (
            self.root / "packages" / "design-playbook" / ".codex-plugin" / "plugin.json"
        )
        payload = json.loads(codex_plugin.read_text(encoding="utf-8"))
        payload["version"] = "9.9.9"  # drift off Claude plugin.json
        codex_plugin.write_text(json.dumps(payload), encoding="utf-8")

        result = self.release("--checks", "version")

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("9.9.9", result.stdout)
        self.assertIn("codex", result.stdout.lower())

    def test_dsh_package_version_must_match_main_package(self) -> None:
        dsh_package = (
            self.root / "packages" / "dsh-design-playbook" / "package.json"
        )
        payload = json.loads(dsh_package.read_text(encoding="utf-8"))
        payload["version"] = "9.9.9"
        dsh_package.write_text(json.dumps(payload), encoding="utf-8")

        result = self.release("--checks", "release-group")

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("dsh-design-playbook version '9.9.9'", result.stdout)
        self.assertIn(f"design-playbook version '{CURRENT_VERSION}'", result.stdout)

    def test_dsh_dependency_must_match_main_package_version(self) -> None:
        dsh_package = (
            self.root / "packages" / "dsh-design-playbook" / "package.json"
        )
        payload = json.loads(dsh_package.read_text(encoding="utf-8"))
        payload["dependencies"]["design-playbook"] = "^0.13.0"
        dsh_package.write_text(json.dumps(payload), encoding="utf-8")

        result = self.release("--checks", "release-group")

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("dsh-design-playbook dependency on design-playbook '^0.13.0'", result.stdout)
        self.assertIn(f"expected '^{CURRENT_VERSION}'", result.stdout)

    def test_release_group_check_passes_on_consistent_fixture(self) -> None:
        result = self.release("--checks", "release-group")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("npm release group versions match", result.stdout)

    def test_release_group_check_ignores_main_package_surface(self) -> None:
        # Review finding (c): the DSH workflow gate must enforce lockstep
        # only. Main-package cosmetics (release notes, README badges,
        # marketplace.json) belong to the main workflow's full gate; an old
        # v* tag missing them must not fail a DSH package-only recovery.
        (self.root / CURRENT_NOTES_REL).unlink()
        (self.root / "README.md").write_text("# no badge\n", encoding="utf-8")
        (self.root / "README-zh.md").write_text("# no badge\n", encoding="utf-8")

        result = self.release("--checks", "release-group")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("npm release group versions match", result.stdout)


if __name__ == "__main__":
    unittest.main()
