"""Shared leaf helpers for bundled MCP adapters (logging and timestamps).

Logging lived under ``mcp.preview.util`` as ``_log``. Evidence capture
imported that private name across server packages. The helpers live here
so the direction no longer pretends they belong to Preview.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
