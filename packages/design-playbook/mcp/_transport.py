"""Shared stdio JSON-RPC framing for the bundled MCP servers.

Both the preview and evidence adapters speak the same wire format
(Content-Length- or newline-delimited JSON-RPC over stdio); this module
owns that framing once so the two servers keep it in lockstep (ADR-0009
bundled layout). Each server runs in its own process, so the module-level
framing state is per-process and never shared across servers.

Policy is deliberately per-server and not here: ``read_message`` raises on
a bad frame, and each ``serve()`` decides whether to reply -32700 and
continue (evidence) or let it propagate (preview).
"""
from __future__ import annotations

import json
import sys
from typing import Any

STDIO_FRAMING_CONTENT_LENGTH = "content-length"
STDIO_FRAMING_NEWLINE = "newline"
_stdio_framing: str | None = None


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
