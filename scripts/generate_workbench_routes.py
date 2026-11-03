#!/usr/bin/env python3
"""Generate the workbench client's route table from its Python owner.

``packages/design-playbook-workbench/design_playbook_workbench/client_routes.py``
is the single owner of the paths the browser calls. The client copy is derived
here, so a route rename that misses ``web/app.js`` turns the drift gate red
instead of failing only in a browser test.

The artifact is a plain script (no build step) attaching one namespace to
``window.DPBUI``; ``web/app.html`` loads it ahead of ``app.js``.
"""
from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_PKG = _ROOT / "packages" / "design-playbook-workbench"
_PKG_SRC = _PKG / "design_playbook_workbench"

SOURCE_PATH = _PKG_SRC / "client_routes.py"
OUT_PATH = _PKG_SRC / "web" / "routes.js"

_HEADER = """\
// Generated from design_playbook_workbench/client_routes.py by
// scripts/generate_workbench_routes.py. DO NOT EDIT: regenerate instead.
// The drift gate compares this artifact byte for byte against a fresh run.
(function (global) {
  "use strict";
  var DPBUI = (global.DPBUI = global.DPBUI || {});
  DPBUI.workbenchRoutes = {
"""

_FOOTER = """\
  };
})(window);
"""

_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def _load_source():
    spec = importlib.util.spec_from_file_location("workbench_client_routes", SOURCE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _builder(name: str, template: str) -> str:
    params = _PLACEHOLDER.findall(template)
    pieces = _PLACEHOLDER.split(template)
    # split() yields [literal, param, literal, param, ..., literal]
    expression = f'"{pieces[0]}"'
    for index, param in enumerate(params, start=1):
        expression += f" + encodeURIComponent({param}) + \"{pieces[index * 2]}\""
    signature = ", ".join(params)
    return (
        f"    {name}: function ({signature}) {{\n"
        f"      return {expression};\n"
        f"    }},\n"
    )


def build(routes) -> list[str]:
    lines = [_HEADER]
    for name in ("API", "STATUS", "RESOLVE", "PROJECTS", "PROBE", "BACKUP", "SESSION"):
        lines.append(f'    {name}: "{getattr(routes, name)}",\n')
    for name, template in routes.BUILDERS:
        lines.append(_builder(name, template))
    lines.append(_FOOTER)
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate the workbench client route table."
    )
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    out = parser.parse_args(argv).out
    out.write_text("".join(build(_load_source())), encoding="utf-8", newline="\n")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(_ROOT / "packages" / "design-playbook"))
    from design_playbook.scripts.stdio_encoding import configure_piped_utf8

    configure_piped_utf8()
    raise SystemExit(main())
