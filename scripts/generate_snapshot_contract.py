#!/usr/bin/env python3
"""Generate the Run Console's snapshot shape constants from the schema.

``mcp/run_console/snapshot_v1.schema.json`` is the single owner of the
seven-part snapshot shape (ADR-0038). The Console client has to know that same
shape to refuse a response that is not a snapshot, and a hand-copied list there
is a second owner that nothing keeps honest. This script derives the client's
copy from the schema, so a section added to the schema and missed here turns the
drift gate red instead of silently letting the client accept a partial shape.

The artifact is a plain script (no build step, ADR-0048) attaching one namespace
to ``window.DPBUI``; ``app.html`` loads it ahead of ``app.js``.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_PKG = _ROOT / "packages" / "design-playbook"

SCHEMA_PATH = _PKG / "mcp" / "run_console" / "snapshot_v1.schema.json"
OUT_PATH = _PKG / "mcp" / "run_console" / "snapshot_contract.js"

_HEADER = """\
// Generated from mcp/run_console/snapshot_v1.schema.json by
// scripts/generate_snapshot_contract.py. DO NOT EDIT: regenerate instead.
// The drift gate compares this artifact byte for byte against a fresh run.
(function (global) {
  "use strict";
  var DPBUI = (global.DPBUI = global.DPBUI || {});
  DPBUI.snapshotContract = {
"""

_FOOTER = """\
  };
})(window);
"""

#: ``schemaVersion`` is checked on its own, so it is not a section.
_VERSION_KEY = "schemaVersion"


def build(schema: dict) -> tuple[int, list[str]]:
    version = schema["properties"][_VERSION_KEY]["const"]
    sections = [name for name in schema["required"] if name != _VERSION_KEY]
    return version, sections


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate the Run Console snapshot shape contract.")
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    out = parser.parse_args(argv).out
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    version, sections = build(schema)
    items = ", ".join(f'"{name}"' for name in sections)
    lines = [
        _HEADER,
        f"    SCHEMA_VERSION: {version},\n",
        f"    REQUIRED_SECTIONS: [{items}],\n",
        _FOOTER,
    ]
    out.write_text("".join(lines), encoding="utf-8", newline="\n")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(_PKG))
    from design_playbook.scripts.stdio_encoding import configure_piped_utf8

    configure_piped_utf8()
    raise SystemExit(main())
