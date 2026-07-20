#!/usr/bin/env python3
"""Black-box regression tests for the release gate."""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "scripts" / "release.py"


def _run(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*args], cwd=cwd, capture_output=True, text=True, check=False,
    )


class ReleaseGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        shutil.copytree(ROOT / "scripts", self.root / "scripts")
        shutil.copytree(
            ROOT / "packages" / "design-playbook",
            self.root / "packages" / "design-playbook",
        )
        shutil.copytree(ROOT / ".claude-plugin", self.root / ".claude-plugin")
        shutil.copy2(ROOT / "README.md", self.root / "README.md")
        shutil.copy2(ROOT / "README-zh.md", self.root / "README-zh.md")
        (self.root / "docs" / "releases").mkdir(parents=True)
        shutil.copy2(
            ROOT / "docs" / "releases" / "v0.3.0.md",
            self.root / "docs" / "releases" / "v0.3.0.md",
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
        tagged = _run("git", "tag", "v0.3.0", cwd=self.root)
        self.assertEqual(tagged.returncode, 0, tagged.stderr)

        result = self.release("--checks", "tree,tag")

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("tag v0.3.0 already points at HEAD", result.stdout)

    def test_release_notes_for_version_are_required(self) -> None:
        (self.root / "docs" / "releases" / "v0.3.0.md").unlink()

        result = self.release("--checks", "version")

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("docs/releases/v0.3.0.md", result.stdout)


if __name__ == "__main__":
    unittest.main()
