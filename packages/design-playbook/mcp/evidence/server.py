#!/usr/bin/env python3
"""Minimal stdio MCP server: single tool `execute_capture_plan`.

Evidence Provider adapter (ticket 02). Captures artifacts via Playwright.
Never writes manifest.jsonl; never accepts criterion refs (orchestrator binds).
Returns relative ``artifact`` plus absolute ``written_path`` so RUN_ROOT/cwd
misconfig is visible to the orchestrator.

Run (plugin-bundled MCP config uses ${CLAUDE_PLUGIN_ROOT}):
  { "command": "python", "args": ["<plugin>/mcp/evidence/server.py"],
    "env": {"DESIGN_PLAYBOOK_RUN_ROOT": "."} }
  DESIGN_PLAYBOOK_RUN_ROOT="." is process-cwd-relative — point it at the
  absolute run root when the host workspace is not the MCP cwd.
Compatibility launcher remains at packages/design-playbook-evidence/server.py.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

# Shared stdio JSON-RPC framing lives one level up in mcp/_transport.py
# (both bundled adapters speak the same wire format; ADR-0009).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _transport import read_message, write_message  # noqa: E402

TOOL_NAME = "execute_capture_plan"
SERVER_NAME = "design-playbook-evidence"
SERVER_VERSION = "0.1.0"
CAPTURE_TYPES = frozenset({"screenshot", "a11y tree", "interaction trace"})
ALLOWED_ARGUMENTS = frozenset({"url", "type", "state", "actions", "artifact_path"})
RUN_ROOT_ENV = "DESIGN_PLAYBOOK_RUN_ROOT"


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _tool_schema() -> dict[str, Any]:
    return {
        "name": TOOL_NAME,
        "description": (
            "Execute a capture plan snapshot: navigate, run actions, write one "
            "artifact (screenshot / a11y tree / interaction trace). Returns "
            "capture result only (artifact, observed_state, result, error, "
            "written_path absolute) — never writes manifest; never judges criteria."
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
                        "Relative artifact path under the configured run root. "
                        "Provider only writes this file."
                    ),
                },
            },
            "required": ["url", "type", "state", "artifact_path"],
            "additionalProperties": False,
        },
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


def _failed(
    artifact: str, error: str, written_path: str = "",
) -> dict[str, Any]:
    """Capture failure payload.

    ``written_path`` is the absolute path under the resolved run root when
    known (empty when path resolution never ran). Callers must not treat a
    non-empty path as proof the file exists — only as where the write was
    attempted. Exposing the absolute path makes cwd / RUN_ROOT misconfig
    visible to the orchestrator without a post-hoc filesystem search.
    """
    return {
        "artifact": artifact,
        "observed_state": "unknown",
        "result": "failed",
        "error": error,
        "written_path": written_path,
    }


def _captured(
    artifact: str, observed_state: str, written_path: str,
) -> dict[str, Any]:
    """Successful capture payload.

    ``written_path`` is always the absolute path of the written artifact
    (resolved under DESIGN_PLAYBOOK_RUN_ROOT or process cwd). Relative
    ``artifact`` stays the run-root-relative path for manifest binding.
    """
    return {
        "artifact": artifact,
        "observed_state": observed_state,
        "result": "captured",
        "error": "",
        "written_path": written_path,
    }


def _run_root() -> Path:
    configured = os.environ.get(RUN_ROOT_ENV)
    return Path(configured).resolve() if configured else Path.cwd().resolve()


def _resolve_artifact_path(artifact_path: str) -> Path:
    requested = Path(artifact_path)
    if (
        requested.is_absolute()
        or PureWindowsPath(artifact_path).is_absolute()
        or PurePosixPath(artifact_path).is_absolute()
    ):
        raise ValueError("artifact_path must be relative to the configured run root")

    root = _run_root()
    candidate = (root / requested).resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("artifact_path escapes the configured run root") from exc
    return candidate


def _run_actions(page: Any, actions: list[dict[str, Any]]) -> None:
    for i, action in enumerate(actions):
        if not isinstance(action, dict):
            raise ValueError(f"actions[{i}] must be an object")
        do = action.get("do")
        if not isinstance(do, str) or not do.strip():
            raise ValueError(f"actions[{i}].do is required")
        do = do.strip().lower()
        selector = action.get("selector")
        if do == "click":
            if not isinstance(selector, str) or not selector:
                raise ValueError(f"actions[{i}].selector required for click")
            page.click(selector, timeout=10_000)
        elif do in ("fill", "type"):
            if not isinstance(selector, str) or not selector:
                raise ValueError(f"actions[{i}].selector required for {do}")
            value = action.get("value")
            if value is None:
                value = action.get("text", "")
            if not isinstance(value, str):
                raise ValueError(f"actions[{i}].value must be a string")
            if do == "fill":
                page.fill(selector, value, timeout=10_000)
            else:
                page.click(selector, timeout=10_000)
                page.keyboard.type(value)
        elif do == "press":
            key = action.get("key") or action.get("value")
            if not isinstance(key, str) or not key:
                raise ValueError(f"actions[{i}].key required for press")
            if isinstance(selector, str) and selector:
                page.press(selector, key, timeout=10_000)
            else:
                page.keyboard.press(key)
        elif do == "wait_for_selector":
            if not isinstance(selector, str) or not selector:
                raise ValueError(
                    f"actions[{i}].selector required for wait_for_selector"
                )
            page.wait_for_selector(selector, timeout=10_000)
        elif do == "wait_for_state":
            state = action.get("state")
            if not isinstance(state, str) or not state:
                raise ValueError(f"actions[{i}].state required for wait_for_state")
            # Prefer explicit selector; else body[data-state].
            if isinstance(selector, str) and selector:
                page.wait_for_selector(selector, timeout=10_000)
            else:
                page.wait_for_selector(
                    f'[data-state="{state}"]',
                    timeout=10_000,
                )
        elif do in ("wait", "sleep"):
            ms = action.get("ms")
            if ms is None:
                ms = action.get("timeout_ms", 200)
            page.wait_for_timeout(int(ms))
        elif do == "select_option":
            # Native <select> — page.fill raises "Fill did not work on <select>";
            # select_option drives <option> by value (or visible label) and
            # fires change.
            if not isinstance(selector, str) or not selector:
                raise ValueError(
                    f"actions[{i}].selector required for select_option")
            value = action.get("value")
            label = action.get("label")
            if value is None and label is None:
                raise ValueError(
                    f"actions[{i}].value or label required for select_option")
            if value is not None:
                page.select_option(selector, value=value, timeout=10_000)
            else:
                page.select_option(selector, label=label, timeout=10_000)
        else:
            raise ValueError(f"actions[{i}]: unsupported do={do!r}")


def _read_observed_state(page: Any) -> str:
    try:
        value = page.evaluate(
            """() => {
              const body = document.body;
              if (body && body.dataset && body.dataset.state) {
                return body.dataset.state;
              }
              const root = document.documentElement;
              if (root && root.dataset && root.dataset.state) {
                return root.dataset.state;
              }
              const el = document.querySelector("[data-state]");
              if (el && el.getAttribute("data-state")) {
                return el.getAttribute("data-state");
              }
              return null;
            }"""
        )
        if isinstance(value, str) and value.strip():
            return value.strip()
    except Exception as exc:  # noqa: BLE001 ? report an honest unknown
        _log(f"observed_state probe failed: {exc}")
    return "unknown"

def _write_screenshot(page: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(path), full_page=True)


def _write_a11y_tree(page: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Playwright removed page.accessibility; aria_snapshot is the v1 tree.
    if hasattr(page, "aria_snapshot"):
        tree = page.aria_snapshot()
        payload: Any = {"format": "aria_snapshot", "tree": tree}
    elif hasattr(page, "accessibility"):
        payload = page.accessibility.snapshot()
    else:
        raise RuntimeError("page has no aria_snapshot/accessibility API")
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _write_interaction_trace(
    context: Any, page: Any, path: Path, actions: list[dict[str, Any]]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Restart tracing for this capture only.
    try:
        context.tracing.stop()
    except Exception:  # noqa: BLE001 — may not have started
        pass
    context.tracing.start(screenshots=True, snapshots=True, sources=False)
    try:
        _run_actions(page, actions)
        context.tracing.stop(path=str(path))
    except Exception:
        try:
            context.tracing.stop()
        except Exception:  # noqa: BLE001
            pass
        raise


def execute_capture_plan(args: dict[str, Any]) -> dict[str, Any]:
    unknown = sorted(set(args) - ALLOWED_ARGUMENTS)
    if unknown:
        names = ", ".join(unknown)
        raise ValueError(
            f"unsupported argument(s): {names}; provider accepts Runtime Object fields only"
        )

    url = args.get("url")
    cap_type = args.get("type")
    state = args.get("state")
    actions = args.get("actions")
    artifact_path = args.get("artifact_path")

    if not isinstance(url, str) or not url.strip():
        raise ValueError("url is required")
    if not isinstance(cap_type, str) or cap_type not in CAPTURE_TYPES:
        raise ValueError(
            f'type must be one of {sorted(CAPTURE_TYPES)}; got {cap_type!r}'
        )
    if not isinstance(state, str) or not state.strip():
        raise ValueError("state is required")
    if not isinstance(artifact_path, str) or not artifact_path.strip():
        raise ValueError("artifact_path is required")
    if actions is None:
        actions = []
    if not isinstance(actions, list):
        raise ValueError("actions must be an array")
    for i, a in enumerate(actions):
        if not isinstance(a, dict):
            raise ValueError(f"actions[{i}] must be an object")

    rel = artifact_path.strip()
    try:
        out_path = _resolve_artifact_path(rel)
    except ValueError as exc:
        return _failed(rel, str(exc))
    abs_written = str(out_path)
    # Refuse every case variant of the manifest execution-record SSOT.
    if out_path.name.casefold() == "manifest.jsonl":
        return _failed(rel, "provider never writes manifest.jsonl", abs_written)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        return _failed(
            rel,
            f"playwright not installed: {exc}",
            abs_written,
        )

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                context = browser.new_context(viewport={"width": 1280, "height": 800})
                page = context.new_page()
                page.goto(url.strip(), wait_until="domcontentloaded", timeout=30_000)

                if cap_type == "interaction trace":
                    _write_interaction_trace(context, page, out_path, actions)
                else:
                    _run_actions(page, actions)
                    if cap_type == "screenshot":
                        _write_screenshot(page, out_path)
                    elif cap_type == "a11y tree":
                        _write_a11y_tree(page, out_path)

                observed = _read_observed_state(page)
            finally:
                browser.close()
    except Exception as exc:  # noqa: BLE001 — surface as capture failure
        _log(f"capture failed: {exc}")
        return _failed(rel, str(exc), abs_written)

    if not out_path.is_file():
        return _failed(
            rel,
            f"artifact not written: {out_path}",
            abs_written,
        )

    return _captured(rel, observed, abs_written)


def serve() -> None:
    _log(f"{SERVER_NAME} MCP server starting (stdio)")
    while True:
        try:
            msg = read_message()
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError, EOFError) as exc:
            _log(f"MCP parse error: {exc}")
            write_message({
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {exc}"},
            })
            continue
        if msg is None:
            break
        if not isinstance(msg, dict):
            write_message({
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32600, "message": "Invalid Request"},
            })
            continue
        method = msg.get("method")
        msg_id = msg.get("id")
        params = msg.get("params") or {}

        if method == "initialize":
            write_message({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": params.get(
                        "protocolVersion", "2024-11-05"
                    ),
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": SERVER_NAME,
                        "version": SERVER_VERSION,
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
                payload = execute_capture_plan(arguments)
                # Capture failures remain data so the orchestrator can bind them.
                # Schema/contract violations raise and become tool-level errors.
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
    serve()
