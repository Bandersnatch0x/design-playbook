#!/usr/bin/env python3
"""Stdio adapter for the Design Playbook evidence capture runtime."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_PKG_ROOT = Path(__file__).resolve().parents[2]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from design_playbook.mcp._transport import serve_stdio  # noqa: E402
from design_playbook.mcp.evidence.capture_contract import (  # noqa: E402
    capture_contract_schema_fragment,
)
from design_playbook.mcp.evidence.capture_runtime import (  # noqa: E402
    execute_capture_plan,
)

TOOL_NAME = "execute_capture_plan"
SERVER_NAME = "design-playbook-evidence"
SERVER_VERSION = "0.1.0"


def _tool_schema() -> dict[str, Any]:
    contract = capture_contract_schema_fragment()
    return {
        "name": TOOL_NAME,
        "description": (
            "Execute a capture plan snapshot under capture contract v1: require "
            "schemaVersion=1 plus explicit viewport, apply deterministic freeze "
            "by default, write one artifact (screenshot / a11y tree / "
            "interaction trace). Returns capture result only (artifact, "
            "observed_state, result, error, written_path, request) — never "
            "writes manifest; never judges criteria."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Target host URL (or file://) to capture.",
                },
                "type": {
                    "type": "string",
                    "description": 'v1: "screenshot" | "a11y tree" | "interaction trace".',
                    "enum": ["screenshot", "a11y tree", "interaction trace"],
                },
                "state": {
                    "type": "string",
                    "description": "Expected page state label (error/loading/ok/...).",
                },
                "actions": {
                    "type": "array",
                    "description": (
                        "Trigger sequence until state (may be empty). Each "
                        "action is an object: do=click|fill|type|press|"
                        "select_option|wait_for_selector|wait_for_state|wait "
                        "with selector (click/fill/type/press/select_option/"
                        "wait_for_selector), value/label (fill/type/select_option), "
                        "key (press), state (wait_for_state), ms (wait). "
                        "select_option drives a native <select> by option value "
                        "(or visible label) and fires change."
                    ),
                    "items": {"type": "object"},
                },
                "artifact_path": {
                    "type": "string",
                    "description": (
                        "Relative artifact path under the evidence/ subtree of "
                        "the configured run root (must already start with "
                        "'evidence/'). Provider only writes this file."
                    ),
                },
                "overwrite": {
                    "type": "boolean",
                    "description": (
                        "Opt in to replacing an existing artifact. Default "
                        "false: an existing file is refused (G6 write boundary)."
                    ),
                    "default": False,
                },
                **contract["properties"],
            },
            "required": [
                "url",
                "type",
                "state",
                "artifact_path",
                *contract["required"],
            ],
            "additionalProperties": False,
        },
    }


if __name__ == "__main__":
    serve_stdio(
        SERVER_NAME,
        SERVER_VERSION,
        _tool_schema(),
        execute_capture_plan,
        recover_from_malformed=True,
    )
