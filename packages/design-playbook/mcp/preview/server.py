#!/usr/bin/env python3
"""Minimal stdio MCP server: single tool ``preview_prototype``.

Entry point only: JSON-RPC stdio framing + tool dispatch. The browser
window, HTTP decide form, control-bar template, and ADR-0008 floor logic
live in the sibling modules (browser.py, control.py, confirm.py, util.py,
i18n.py). No third-party deps.

Run (plugin-bundled MCP config uses ${CLAUDE_PLUGIN_ROOT}):
  { "command": "python", "args": ["<plugin>/mcp/preview/server.py"] }
Compatibility launcher remains at packages/design-playbook-preview/server.py.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# Shared stdio JSON-RPC framing lives one level up in mcp/_transport.py
# (both bundled adapters speak the same wire format; ADR-0009).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _transport import read_message, write_message  # noqa: E402

from i18n import default_options
from util import _log

# Confirm/floor records + prototype target resolution + self-check.
from confirm import (  # noqa: F401  (re-exported for stable module surface)
    _append_log,
    _check_feedback_floor,
    _ensure_prototype,
    _preview_dir_for,
    _self_check_floor,
    _write_confirm,
)
# Control-bar template + builder + feedback formatting.
from control import _build_control, _format_feedback, control_tpl  # noqa: F401
# Owned-Chromium window + HTTP decide form + browser/HTTP helpers
# (re-exported so external callers and tests that import ``server`` keep
# resolving names that previously lived here).
from browser import (  # noqa: F401
    BaseHTTPRequestHandler,
    HTTPServer,
    _browser_candidates,
    _collect_via_browser,
    _done_page_html,
    _kill_browser_proc,
    _open_preview_window,
    _parse_anchors,
    _request_browser_window_close,
    _rm_tree,
    _screen_size,
    _stop_http_server,
    subprocess,
    tempfile,
)

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

    preview_dir = _preview_dir_for(Path(path_arg) if path_arg else None)
    prototype = _ensure_prototype(
        path_arg, html, round_n, preview_dir)

    decision = _collect_via_browser(prototype, summary.strip(), options, round_n)
    floor_pass = bool(decision.get("floor_pass"))
    floor_failure = str(decision.get("floor_failure") or "")
    # ADR-0008: a confirm whose feedback fails the structural floor is NOT
    # authoritative — write the record with confirmed=false + floor_failure
    # (single source of truth on disk and in payload) so the orchestrator
    # treats it as not-yet-confirmed (revise) instead of advancing to Fill.
    user_confirmed = bool(decision["confirmed"]) and not decision["aborted"]
    confirmed = user_confirmed and floor_pass
    confirm_path = ""
    if user_confirmed:
        out = _write_confirm(
            preview_dir,
            round_n=round_n,
            report_ref=report_ref.strip(),
            selected=decision["selected_options"],
            feedback=decision["feedback"],
            prototype_html_hash=decision["prototype_html_hash"],
            confirmed=confirmed,
            floor_pass=floor_pass,
            floor_failure=floor_failure,
        )
        confirm_path = str(out)
    _append_log(
        preview_dir,
        round_n=round_n,
        report_ref=report_ref.strip(),
        feedback=decision["feedback"],
        aborted=bool(decision["aborted"]),
        selected=list(decision["selected_options"]),
        anchors=list(decision.get("anchors") or []),
        floor_pass=floor_pass,
        floor_failure=floor_failure,
        rejected=bool(decision.get("rejected")),
        rejection=str(decision.get("rejection") or ""),
    )
    return {
        "confirmed": confirmed,
        "floor_pass": floor_pass,
        "selected_options": list(decision["selected_options"]),
        "feedback": decision["feedback"],
        "anchors": list(decision.get("anchors") or []),
        "round": round_n,
        "confirm_record_path": confirm_path,
        "aborted": bool(decision["aborted"]),
    }



def _result_text(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(payload, ensure_ascii=False, indent=2),
            }
        ],
        "structuredContent": payload,
        "isError": False,
    }



def _error_result(message: str) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": message}],
        "isError": True,
    }



def serve() -> None:
    _log("design-playbook-preview MCP server starting (stdio)")
    while True:
        msg = read_message()
        if msg is None:
            break
        method = msg.get("method")
        msg_id = msg.get("id")
        params = msg.get("params") or {}

        if method == "initialize":
            write_message({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": params.get(
                        "protocolVersion", "2024-11-05"),
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "design-playbook-preview",
                        "version": "0.1.0",
                    },
                },
            })
            continue

        if method == "notifications/initialized":
            continue

        if method == "tools/list":
            write_message({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"tools": [_tool_schema()]},
            })
            continue

        if method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments") or {}
            if name != TOOL_NAME:
                write_message({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": _error_result(f"unknown tool: {name}"),
                })
                continue
            try:
                payload = handle_preview_prototype(arguments)
                write_message({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": _result_text(payload),
                })
            except Exception as exc:  # noqa: BLE001 — return to client
                _log(f"tools/call error: {exc}")
                write_message({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": _error_result(str(exc)),
                })
            continue

        if method == "ping":
            write_message({"jsonrpc": "2.0", "id": msg_id, "result": {}})
            continue

        if msg_id is not None:
            write_message({
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {method}",
                },
            })




if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--self-check":
        _self_check_floor()
    else:
        serve()
