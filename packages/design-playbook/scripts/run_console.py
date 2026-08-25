#!/usr/bin/env python3
"""Serve the secured single-run read API for one explicit run root.

Binds one IP-literal loopback address on an ephemeral port, prints the
session URL and bearer token exactly once (the human delivery channel),
serves authenticated GET/HEAD reads until interrupted, then invalidates
the token and every locator (RCV1-006).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent
_PKG_ROOT = _SCRIPTS_DIR.parent
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from design_playbook.mcp.run_console.http_server import RunConsoleHTTPServer  # noqa: E402
from design_playbook.mcp.run_console.request_security import LOOPBACK_BIND_HOSTS  # noqa: E402
from design_playbook.mcp.run_console.session import (  # noqa: E402
    RunConsoleSession,
    RunConsoleSessionError,
)

_LAUNCH_LINE = "Run console: {origin} token: {token}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run-console",
        description="Serve the secured single-run read API for one run root",
    )
    parser.add_argument(
        "run_root",
        help="path to the selected run root",
    )
    parser.add_argument(
        "--host",
        default=LOOPBACK_BIND_HOSTS[0],
        choices=LOOPBACK_BIND_HOSTS,
        help="IP-literal loopback address to bind (default: %(default)s)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="port to bind; 0 selects an ephemeral port (default: 0)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        session = RunConsoleSession(run_root=args.run_root)
    except (RunConsoleSessionError, OSError) as exc:
        print(f"run-console: {exc}", file=sys.stderr)
        return 2
    try:
        server = RunConsoleHTTPServer(session, bind_host=args.host, port=args.port)
    except (OSError, ValueError) as exc:
        session.close()
        print(f"run-console: {exc}", file=sys.stderr)
        return 2
    # The one and only stdout line: URL plus token, printed once at launch.
    print(_LAUNCH_LINE.format(origin=server.origin, token=session.token))
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
