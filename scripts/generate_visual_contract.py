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

import argparse
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the visual-edit wire contract.")
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    out = parser.parse_args(argv).out
    lines = [_HEADER]
    # Only values a client reads are emitted. CHANGE_KINDS, EDIT_SOURCES,
    # CONTENT_PROPERTIES, MAX_EDITS, MAX_SELECTOR and MAX_VALUE are server-side
    # validation limits with no client reader; shipping them invited a second
    # copy that nothing kept honest.
    lines.append(_js_int("SCHEMA_VERSION", visual_batch.SCHEMA_VERSION))
    lines.append(_js_str("STATUS_PENDING", visual_batch.STATUS_PENDING))
    lines.append(_js_str("STATUS_STALE", visual_batch.STATUS_STALE))
    lines.append(_js_str_tuple("CSS_KINDS", visual_batch.CSS_KINDS))
    lines.append(_js_str_tuple("VIEWPORTS", visual_batch.VIEWPORTS))
    lines.append(_js_str("SHELL_SOURCE", visual_batch.SHELL_SOURCE))
    lines.append(_js_str("FRAME_SOURCE", visual_batch.FRAME_SOURCE))
    lines.append(_js_str("ANY_VIEWPORT", visual_batch.VIEWPORTS[-1]))
    lines.append(_FOOTER)
    out.write_text("".join(lines), encoding="utf-8", newline="\n")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    import sys

    sys.path.insert(0, str(_ROOT / "packages" / "design-playbook"))
    from design_playbook.scripts.stdio_encoding import configure_piped_utf8

    configure_piped_utf8()
    raise SystemExit(main())
