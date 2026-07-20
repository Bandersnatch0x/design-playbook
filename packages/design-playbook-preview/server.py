#!/usr/bin/env python3
"""Compatibility launcher for the Preview MCP adapter.

Runtime lives in the redistributable plugin package so marketplace installs
get ``preview_prototype`` without a second package. This sibling entrypoint
keeps existing monorepo / local MCP configs working.
"""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

TARGET = (
    Path(__file__).resolve().parents[1]
    / "design-playbook"
    / "mcp"
    / "preview"
    / "server.py"
)


def main() -> None:
    if not TARGET.is_file():
        sys.stderr.write(f"preview runtime missing: {TARGET}\n")
        raise SystemExit(2)
    sys.path.insert(0, str(TARGET.parent))
    sys.argv[0] = str(TARGET)
    runpy.run_path(str(TARGET), run_name="__main__")


if __name__ == "__main__":
    main()
