#!/usr/bin/env python3
"""Install the local gate hooks (scripts/hooks/*) into the live git hooks dir.

Leaves unrelated hooks (e.g. tracker hooks under other names) untouched, and
refuses to overwrite a hook it did not install itself (marker line check).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

MARKER = "design-playbook local gate"
REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_SRC = REPO_ROOT / "scripts" / "hooks"


def live_hooks_dir() -> Path:
    out = subprocess.run(
        ["git", "rev-parse", "--git-path", "hooks"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    path = Path(out)
    return path if path.is_absolute() else REPO_ROOT / path


def main() -> int:
    dest_dir = live_hooks_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    for src in sorted(HOOKS_SRC.iterdir()):
        if not src.is_file():
            continue
        dest = dest_dir / src.name
        if dest.exists() and MARKER not in dest.read_text(
            encoding="utf-8", errors="replace"
        ):
            print(
                f"refusing to overwrite {dest}: existing hook was not installed by this script",
                file=sys.stderr,
            )
            return 1
        shutil.copyfile(src, dest)
        dest.chmod(0o755)
        print(f"installed {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
