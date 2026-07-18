"""Shared leaf helpers for the preview adapter (logging, timestamps).

Sibling to i18n.py; imported by server.py, browser.py, confirm.py.
No third-party deps.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)



def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

