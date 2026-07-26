#!/usr/bin/env python3
"""Minimal stdio MCP server: single tool ``preview_prototype``.

Entry point only: tool schema + handler. JSON-RPC stdio framing lives in
``mcp/_transport.py``; browser HTTP collection lives in ``browser.py``;
decision authority and persistence live in ``transaction.py``. Control,
confirm, utility, and locale details stay in their sibling modules. No
third-party deps.

Run (plugin-bundled MCP config uses ${CLAUDE_PLUGIN_ROOT}):
  { "command": "python", "args": ["<plugin>/mcp/preview/server.py"] }
Compatibility launcher remains at packages/design-playbook-preview/server.py.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Shared stdio JSON-RPC framing + single-tool dispatch live one level up in
# mcp/_transport.py (both bundled adapters speak the same wire format and
# run the same JSON-RPC protocol; ADR-0009).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _transport import serve_stdio  # noqa: E402

import browser
from confirm import _self_check_floor
from i18n import default_options
from transaction import run_preview_transaction

TOOL_NAME = "preview_prototype"



def _tool_schema() -> dict[str, Any]:
    return {
        "name": TOOL_NAME,
        "description": (
            "Show a disposable HTML prototype in a centered app window, collect "
            "user confirm/revise feedback, and write preview confirm records."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute path to prototype HTML (preferred).",
                },
                "html": {
                    "type": "string",
                    "description": "Inline full-page HTML when path is absent.",
                },
                "summary": {
                    "type": "string",
                    "description": "Decision-report summary / change note.",
                },
                "round": {
                    "type": "integer",
                    "description": "Loop round number; first round = 1.",
                },
                "report_ref": {
                    "type": "string",
                    "description": "Path or version id of the decision report.",
                },
                "options": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Confirm/revise labels. Omit to use the adapter locale's "
                        "defaults; known confirm/revise labels are rendered in "
                        "the adapter locale either way."
                    ),
                },
            },
            "required": ["summary", "round", "report_ref"],
        },
    }



def handle_preview_prototype(args: dict[str, Any]) -> dict[str, Any]:
    path_arg = args.get("path")
    html = args.get("html")
    summary = args.get("summary")
    round_n = args.get("round")
    report_ref = args.get("report_ref")
    options = args.get("options") or default_options()

    if not isinstance(summary, str) or not summary.strip():
        raise ValueError("summary is required")
    if not isinstance(round_n, int) or isinstance(round_n, bool) or round_n < 1:
        raise ValueError("round must be a positive integer")
    if not isinstance(report_ref, str) or not report_ref.strip():
        raise ValueError("report_ref is required")
    if path_arg is not None and not isinstance(path_arg, str):
        raise ValueError("path must be a string")
    if html is not None and not isinstance(html, str):
        raise ValueError("html must be a string")
    if not isinstance(options, list) or not all(isinstance(o, str) for o in options):
        raise ValueError("options must be string[]")

    return run_preview_transaction(
        path_arg=path_arg,
        html=html,
        summary=summary,
        round_n=round_n,
        report_ref=report_ref,
        options=options,
        collect=browser._collect_via_browser,
    )


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--self-check":
        _self_check_floor()
    else:
        serve_stdio(
            "design-playbook-preview",
            "0.1.0",
            _tool_schema(),
            handle_preview_prototype,
            recover_from_malformed=False,
        )
