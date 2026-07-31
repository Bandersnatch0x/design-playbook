"""Shared leaf helpers for the preview adapter (logging, timestamps, digest).

Sibling to i18n.py; imported by server.py, browser.py, transaction.py.
No third-party deps.
"""
from __future__ import annotations

import hashlib
import sys
from datetime import datetime, timezone


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def prototype_html_digest(raw: bytes) -> str:
    """SHA-256 of prototype bytes with newlines normalized to LF.

    Windows ``core.autocrlf`` rewrites working-tree bytes on checkout; a raw
    digest then disagrees between the machine that wrote the confirm record
    and a Linux CI runner validating the same git blob. Line-ending noise is
    not a prototype content change for G5 integrity (issue 02 / T01).

    Must stay in lockstep with ``scripts/_preview_integrity.prototype_html_digest``.
    """
    return hashlib.sha256(
        raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    ).hexdigest()



def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

