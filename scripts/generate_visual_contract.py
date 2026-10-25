#!/usr/bin/env python3
"""Generate the front-end visual-edit contract constants from the server module.

ADR-0048 requires front-end contract constants to be generated from the server
module and compared byte for byte against the committed artifact. The server
module ``visual_batch.py`` is the single authority for the wire constants; this
script derives the JS artifact from it, so a constant change that skips the
generator turns the drift gate red instead of silently diverging.

The artifact is a plain script (no build step, ADR-0048) attaching one
namespace to ``window.DPBUI``. The preview shell, the review fragment, the
React editor and the pin bridge load it as its own block ahead of the code
that reads it.
"""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_PKG = _ROOT / "packages" / "design-playbook"
sys.path.insert(0, str(_PKG))
sys.path.insert(0, str(_PKG / "tests"))

from design_playbook.mcp.preview import visual_batch  # noqa: E402

OUT_PATH = _PKG / "mcp" / "preview" / "visual_contract.js"

_HEADER = """\
// Generated from design_playbook/mcp/preview/visual_batch.py by
// scripts/generate_visual_contract.py. DO NOT EDIT: regenerate instead.
// The drift gate compares this artifact byte for byte against a fresh run.
(function (global) {
  "use strict";
  var DPBUI = (global.DPBUI = global.DPBUI || {});
  DPBUI.visualContract = {
"""

_FOOTER = """\
  };
})(window);
"""


def _js_int(name: str, value: int) -> str:
    return f"    {name}: {value},\n"


def _js_str(name: str, value: str) -> str:
    return f'    {name}: "{value}",\n'


def _js_str_tuple(name: str, values: tuple[str, ...]) -> str:
    items = ", ".join(f'"{v}"' for v in values)
    return f"    {name}: [{items}],\n"


def main() -> int:
    lines = [_HEADER]
    lines.append(_js_int("SCHEMA_VERSION", visual_batch.SCHEMA_VERSION))
    lines.append(_js_str("STATUS_PENDING", visual_batch.STATUS_PENDING))
    lines.append(_js_str("STATUS_STALE", visual_batch.STATUS_STALE))
    lines.append(_js_str_tuple("CHANGE_KINDS", visual_batch.CHANGE_KINDS))
    lines.append(_js_str_tuple("CSS_KINDS", visual_batch.CSS_KINDS))
    lines.append(_js_str_tuple("VIEWPORTS", visual_batch.VIEWPORTS))
    lines.append(_js_str_tuple("EDIT_SOURCES", visual_batch.EDIT_SOURCES))
    lines.append(_js_str("SHELL_SOURCE", visual_batch.SHELL_SOURCE))
    lines.append(_js_str("DEFAULT_SOURCE", visual_batch.SHELL_SOURCE))
    lines.append(_js_str_tuple("CONTENT_PROPERTIES", visual_batch.CONTENT_PROPERTIES))
    lines.append(_js_str("ANY_VIEWPORT", visual_batch.VIEWPORTS[-1]))
    lines.append(_js_int("MAX_EDITS", visual_batch.MAX_EDITS))
    lines.append(_js_int("MAX_SELECTOR", visual_batch.MAX_SELECTOR))
    lines.append(_js_int("MAX_VALUE", visual_batch.MAX_VALUE))
    lines.append(_FOOTER)
    OUT_PATH.write_text("".join(lines), encoding="utf-8", newline="\n")
    print(f"wrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
