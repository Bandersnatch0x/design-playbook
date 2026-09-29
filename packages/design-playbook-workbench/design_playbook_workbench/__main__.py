"""``python -m design_playbook_workbench`` / ``design-playbook-workbench``.

Start, stop, and diagnose the local workbench service. The command binds
loopback only, prints the actual bound origin plus the one-time bootstrap
URL, and keeps serving until interrupted; a port that is already in use
is reported as an explicit failure with a non-zero exit code rather than
a misleading success line.
"""
from __future__ import annotations

import argparse
import signal
import sys
import threading
from pathlib import Path

from . import __version__
from .errors import WorkbenchError
from .launcher import describe, start_runtime
from .security import DEFAULT_BIND_HOST, LOOPBACK_BIND_HOSTS
from .store import default_data_dir


def _write_stdout(text: str) -> None:
    """Emit UTF-8 regardless of the host console code page."""
    stream = sys.stdout
    buffer = getattr(stream, "buffer", None)
    if buffer is not None:
        try:
            buffer.write((text + "\n").encode("utf-8"))
            buffer.flush()
            return
        except (OSError, ValueError):  # pragma: no cover - defensive
            pass
    try:
        stream.write(text + "\n")
        stream.flush()
    except UnicodeEncodeError:  # pragma: no cover - legacy consoles
        stream.write(text.encode("ascii", "replace").decode("ascii") + "\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="design-playbook-workbench",
        description=(
            "Local single-maintainer design asset workbench. Binds a loopback "
            "address only; projects are added read-only from the browser UI."
        ),
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help=(
            "Private workbench data directory "
            "(default: the per-user application data directory)."
        ),
    )
    parser.add_argument(
        "--bind-host",
        default=DEFAULT_BIND_HOST,
        choices=list(LOOPBACK_BIND_HOSTS),
        help="Loopback address to bind (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="TCP port (default: 0, choose an ephemeral port).",
    )
    parser.add_argument(
        "--session-ttl-seconds",
        type=int,
        default=None,
        help="Session and bootstrap lifetime in seconds.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    data_dir = Path(arguments.data_dir) if arguments.data_dir else default_data_dir()
    ttl = arguments.session_ttl_seconds
    extra: dict[str, int] = {}
    if ttl is not None:
        extra["ttl_seconds"] = ttl
    try:
        runtime = start_runtime(
            data_dir=data_dir,
            bind_host=arguments.bind_host,
            port=arguments.port,
            **extra,
        )
    except OSError as error:
        _write_stdout(
            f"design-playbook-workbench: cannot bind "
            f"{arguments.bind_host}:{arguments.port} ({error}). "
            "Choose another --port or stop the process using it."
        )
        return 2
    except WorkbenchError as error:
        _write_stdout(f"design-playbook-workbench: {error.code}: {error}")
        return 3

    _write_stdout(describe(runtime))
    stopped = threading.Event()

    def _request_stop(signum: int, frame: object) -> None:  # pragma: no cover - signal
        stopped.set()

    for name in ("SIGINT", "SIGTERM", "SIGBREAK"):
        handler = getattr(signal, name, None)
        if handler is not None:
            try:
                signal.signal(handler, _request_stop)
            except (ValueError, OSError):  # pragma: no cover - non-main thread
                pass
    try:
        stopped.wait()
    except KeyboardInterrupt:  # pragma: no cover - console interrupt
        pass
    finally:
        runtime.stop()
    return 0


if __name__ == "__main__":  # pragma: no cover - module entry
    raise SystemExit(main())
