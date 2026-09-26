#!/usr/bin/env python3
"""Cross-platform Codex skill installer for design-playbook.

Creates (or refreshes) symlinks under ``~/.codex/skills/<name>`` pointing at
this package's ``skills/*`` directories. Falls back to directory copy when
symlinks are unavailable (common on Windows without Developer Mode).
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
SKILLS_SRC = PACKAGE / "skills"
DEFAULT_DEST = Path.home() / ".codex" / "skills"


def install_one(src: Path, dest: Path, *, force: bool) -> str:
    if not src.is_dir():
        return f"skip {src.name}: source missing"
    if dest.exists() or dest.is_symlink():
        if not force:
            return f"skip {src.name}: {dest} exists (pass --force)"
        if dest.is_symlink() or dest.is_file():
            dest.unlink()
        else:
            shutil.rmtree(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(src, dest, target_is_directory=True)
        return f"link {src.name} -> {dest}"
    except OSError:
        shutil.copytree(src, dest)
        return f"copy {src.name} -> {dest}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install design-playbook skills for Codex")
    parser.add_argument(
        "--dest",
        type=Path,
        default=DEFAULT_DEST,
        help=f"skills directory (default: {DEFAULT_DEST})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace existing skill directories/links",
    )
    args = parser.parse_args(argv)

    if not SKILLS_SRC.is_dir():
        print(f"skills source missing: {SKILLS_SRC}", file=sys.stderr)
        return 2

    print(f"source: {SKILLS_SRC}")
    print(f"dest:   {args.dest}")
    for skill in sorted(p for p in SKILLS_SRC.iterdir() if p.is_dir()):
        print(" ", install_one(skill, args.dest / skill.name, force=args.force))
    print("done. Load design-playbook via Codex skills or @ references.")
    print("MCP: see packages/design-playbook/codex/AGENTS.md")
    return 0


if __name__ == "__main__":
    # One pipe-encoding seam (T-105): UTF-8 on piped stdout/stderr
    # regardless of the host code page. See scripts/stdio_encoding.py.
    for _candidate in Path(__file__).resolve().parents:
        if (_candidate / "design_playbook.py").is_file():
            sys.path.insert(0, str(_candidate))
            break
    from design_playbook.scripts.stdio_encoding import configure_piped_utf8

    configure_piped_utf8()
    sys.exit(main())
