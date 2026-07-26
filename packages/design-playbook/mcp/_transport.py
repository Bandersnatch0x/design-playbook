"""Shared stdio JSON-RPC framing + single-tool dispatch for the bundled MCP servers.

Both the preview and evidence adapters speak the same wire format
(Content-Length- or newline-delimited JSON-RPC over stdio) and run the same
JSON-RPC dispatch (initialize / tools/list / tools/call / ping /
method-not-found). This module owns both once so the two servers keep them in
lockstep (ADR-0009 bundled layout). Each server runs in its own process, so
the module-level framing state is per-process and never shared across servers.

The one policy that is deliberately per-server is malformed-input recovery,
expressed as the ``recover_from_malformed`` flag on :func:`serve_stdio`:
``read_message`` always raises on a bad frame; preview re-raises it
(fail-fast — the server ends), while evidence catches it, replies ``-32700``
/ ``-32600``, and keeps serving (fail-soft — one bad client frame cannot abort
a capture run).
"""
from __future__ import annotations

import json
import sys
from typing import Any, Callable

STDIO_FRAMING_CONTENT_LENGTH = "content-length"
STDIO_FRAMING_NEWLINE = "newline"
_stdio_framing: str | None = None


class ToolError(Exception):
    """Recoverable domain error with MCP structured error content."""

    def __init__(self, message: str, structured_content: dict[str, Any]):
        super().__init__(message)
        self.structured_content = structured_content


def read_message() -> dict[str, Any] | None:
    """Read one Content-Length- or newline-delimited JSON-RPC message.

    Returns None at EOF. Raises json/unicode/value/EOF errors on a bad
    frame; the caller decides the recovery policy (see module docstring).
    """
    global _stdio_framing

    while True:
        first_line = sys.stdin.buffer.readline()
        if not first_line:
            return None
        if first_line not in (b"\r\n", b"\n"):
            break

    if not first_line.lower().startswith(b"content-length:"):
        _stdio_framing = STDIO_FRAMING_NEWLINE
        return json.loads(first_line.decode("utf-8"))

    _stdio_framing = STDIO_FRAMING_CONTENT_LENGTH
    headers: dict[str, str] = {}
    line = first_line
    while line not in (b"\r\n", b"\n"):
        key, separator, value = line.decode("utf-8").partition(":")
        if not separator:
            raise ValueError(f"invalid MCP stdio header: {line!r}")
        headers[key.strip().lower()] = value.strip()
        line = sys.stdin.buffer.readline()
        if not line:
            raise EOFError("MCP stdio headers ended before the blank line")
    length = int(headers.get("content-length", "0"))
    if length <= 0:
        raise ValueError("MCP stdio Content-Length must be positive")
    body = sys.stdin.buffer.read(length)
    if len(body) != length:
        raise EOFError(
            f"MCP stdio body ended early: expected {length}, got {len(body)}"
        )
    return json.loads(body.decode("utf-8"))


def write_message(payload: dict[str, Any]) -> None:
    """Write one JSON-RPC message in the framing detected by read_message."""
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    if _stdio_framing == STDIO_FRAMING_NEWLINE:
        sys.stdout.buffer.write(raw + b"\n")
    else:
        sys.stdout.buffer.write(
            f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii") + raw
        )
    sys.stdout.buffer.flush()


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


def _error_result(
        message: str, structured_content: dict[str, Any] | None = None
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "content": [{"type": "text", "text": message}],
        "isError": True,
    }
    if structured_content is not None:
        result["structuredContent"] = structured_content
    return result


def _exception_result(exc: Exception) -> dict[str, Any]:
    structured = exc.structured_content if isinstance(exc, ToolError) else None
    return _error_result(str(exc), structured)


def serve_stdio(
        server_name: str,
        server_version: str,
        tool_schema: dict[str, Any],
        handle_tool: Callable[[dict[str, Any]], dict[str, Any]],
        *,
        recover_from_malformed: bool) -> None:
    """Run the shared single-tool MCP stdio dispatch loop (ADR-0009).

    Both bundled adapters speak the same JSON-RPC protocol; owning the
    dispatch once here keeps initialize / tools/list / tools/call / ping /
    method-not-found in lockstep instead of copy-pasted in each server.

    ``tool_schema`` is the single advertised tool (its ``name`` is the
    accepted ``tools/call`` name); ``handle_tool`` maps the call's
    ``arguments`` to the payload returned to the client. A raised exception
    becomes a tool-level error result (``isError: true``); a returned dict
    is the structured success payload.

    The one deliberately per-server policy is malformed-input recovery (see
    module docstring):

      * ``recover_from_malformed=False`` (preview): a bad frame or a
        non-object request propagates and ends the server (fail-fast).
      * ``recover_from_malformed=True`` (evidence): reply ``-32700`` (bad
        frame) or ``-32600`` (non-object request) and keep serving, so one
        bad client frame cannot abort a capture run.
    """
    print(f"{server_name} MCP server starting (stdio)",
          file=sys.stderr, flush=True)
    while True:
        try:
            msg = read_message()
        except (json.JSONDecodeError, UnicodeDecodeError,
                ValueError, EOFError) as exc:
            if not recover_from_malformed:
                raise
            print(f"MCP parse error: {exc}", file=sys.stderr, flush=True)
            write_message({
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": f"Parse error: {exc}"},
            })
            continue
        if msg is None:
            break
        if recover_from_malformed and not isinstance(msg, dict):
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
                        "protocolVersion", "2024-11-05"),
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": server_name,
                        "version": server_version,
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
                "result": {"tools": [tool_schema]},
            })
            continue

        if method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments") or {}
            if name != tool_schema["name"]:
                write_message({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": _error_result(f"unknown tool: {name}"),
                })
                continue
            try:
                payload = handle_tool(arguments)
                write_message({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": _result_text(payload),
                })
            except Exception as exc:  # noqa: BLE001 — return to client
                print(f"tools/call error: {exc}", file=sys.stderr, flush=True)
                write_message({
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": _exception_result(exc),
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
