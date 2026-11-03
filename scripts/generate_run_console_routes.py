#!/usr/bin/env python3
"""Generate the Run Console's client-visible routes and action names.

``mcp/run_console/client_routes.py`` is the single owner of the paths, action
names, and payload schema version both the HTTP server and the browser must
agree on (RCV1-009, ADR-0044). The browser copy is derived here, so a rename
that misses the client turns the drift gate red instead of failing only in a
browser test.

The artifact is a plain script (no build step, ADR-0048) attaching one
namespace to ``window.DPBUI``; ``app.html`` loads it ahead of ``app.js``.
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_PKG = _ROOT / "packages" / "design-playbook"

SOURCE_PATH = _PKG / "mcp" / "run_console" / "client_routes.py"
OUT_PATH = _PKG / "mcp" / "run_console" / "client_routes.js"

_HEADER = """\
// Generated from mcp/run_console/client_routes.py by
// scripts/generate_run_console_routes.py. DO NOT EDIT: regenerate instead.
// The drift gate compares this artifact byte for byte against a fresh run.
(function (global) {
  "use strict";
  var DPBUI = (global.DPBUI = global.DPBUI || {});
  DPBUI.runConsoleRoutes = {
"""

_FOOTER = """\
  };
})(window);
"""


def _load_source():
    """Load the constants by path; the module deliberately imports nothing."""
    spec = importlib.util.spec_from_file_location(
        "run_console_client_routes", SOURCE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build(routes) -> list[str]:
    def typed_action(path: str, action: str) -> str:
        return (
            f'{{ path: "{path}", action: "{action}", '
            f"schemaVersion: {routes.SCHEMA_VERSION} }}"
        )

    return [
        _HEADER,
        f"    SCHEMA_VERSION: {routes.SCHEMA_VERSION},\n",
        f'    SNAPSHOT: "{routes.SNAPSHOT_ROUTE}",\n',
        f'    SOURCES_PREFIX: "{routes.SOURCES_PREFIX}",\n',
        "    REFRESH: "
        f"{typed_action(routes.REFRESH_ROUTE, routes.ACTION_REFRESH)},\n",
        "    EXPORT_PREVIEW: "
        f"{typed_action(routes.EXPORT_PREVIEW_ROUTE, routes.ACTION_EXPORT_PREVIEW)},\n",
        "    EXPORT_WRITE: "
        f"{typed_action(routes.EXPORT_WRITE_ROUTE, routes.ACTION_EXPORT_WRITE)},\n",
        _FOOTER,
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate the Run Console client routes contract."
    )
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    out = parser.parse_args(argv).out
    out.write_text("".join(build(_load_source())), encoding="utf-8", newline="\n")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(_PKG))
    from design_playbook.scripts.stdio_encoding import configure_piped_utf8

    configure_piped_utf8()
    raise SystemExit(main())
