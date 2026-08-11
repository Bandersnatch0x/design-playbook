#!/usr/bin/env python3
"""Compatibility launcher for the Evidence MCP adapter.

Runtime lives in the redistributable plugin package so marketplace installs
get ``execute_capture_plan`` without a second package. This sibling entrypoint
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
    / "evidence"
    / "server.py"
)


def main() -> None:
    if not TARGET.is_file():
        sys.stderr.write(f"evidence runtime missing: {TARGET}\n")
        raise SystemExit(2)
    # The bundled server self-bootstraps the design_playbook package root
    # (ADR-0022); no launcher-side path insert needed.
    sys.argv[0] = str(TARGET)
    runpy.run_path(str(TARGET), run_name="__main__")


if __name__ == "__main__":
    main()
