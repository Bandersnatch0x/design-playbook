"""One loopback listener for the workbench's HTTP surfaces.

Both servers in this distribution -- the management API and the preview
origin -- are one IP-literal loopback listener with the same rules: an exact
loopback bind host, no reverse DNS, an authority/origin derived from the
socket that actually bound, and an idempotent stop. Written out twice those
rules drift; the preview copy is the one that carries ADR-0046's origin
exclusivity reasoning.

The teardown is part of the same rule set: half-close, drain the peer's
remaining bytes, then close, so a client body left unread never turns close
into a TCP reset on Windows.
"""
from __future__ import annotations

import http.server
import socket
import socketserver
import threading

from .security import (
    canonical_authority,
    canonical_origin,
    ensure_loopback_bind_host,
)


def finish_gracefully(connection: socket.socket) -> None:
    """Half-close, drain the peer's remaining bytes, then let close happen.

    A client body left unread in the receive buffer (e.g. a POST whose
    Content-Length is absent: the stray bytes parse as garbage request lines
    and the connection must die) turns a plain close() into a TCP reset on
    Windows -- the client gets WinError 10053 mid-read instead of the response
    it was sent.
    """
    try:
        connection.shutdown(socket.SHUT_WR)
    except OSError:
        pass
    try:
        connection.settimeout(0.2)
        while connection.recv(65536):
            pass
    except OSError:
        pass


class LoopbackHTTPServer(http.server.ThreadingHTTPServer):
    """One IP-literal loopback listener with a strict bind and one origin."""

    daemon_threads = True
    allow_reuse_address = False
    serve_thread_name = "loopback-server"

    def __init__(
        self,
        handler: type,
        *,
        bind_host: str,
        port: int = 0,
    ) -> None:
        host = ensure_loopback_bind_host(bind_host)
        if host == "::1":
            self.address_family = socket.AF_INET6
        super().__init__((host, port), handler)
        bound_host, bound_port = self.socket.getsockname()[:2]
        if bound_host != host:
            self.server_close()
            raise OSError("socket did not bind to the requested loopback literal")
        self.bind_host = host
        self.authority = canonical_authority(host, bound_port)
        self.origin = canonical_origin(host, bound_port)
        self._serve_thread: threading.Thread | None = None
        self._stopped = False

    def server_bind(self) -> None:
        # Bind without socket.getfqdn: no reverse DNS and no hostname.
        socketserver.TCPServer.server_bind(self)
        host, port = self.socket.getsockname()[:2]
        self.server_name = host
        self.server_port = port

    @property
    def port(self) -> int:
        return self.socket.getsockname()[1]

    def start_serving(self, poll_interval: float = 0.05) -> "LoopbackHTTPServer":
        """Serve forever on a daemon thread; idempotent while it runs."""
        if self._serve_thread is not None and self._serve_thread.is_alive():
            return self
        self._serve_thread = threading.Thread(
            target=self.serve_forever,
            kwargs={"poll_interval": poll_interval},
            daemon=True,
            name=self.serve_thread_name,
        )
        self._serve_thread.start()
        return self

    def stop(self) -> None:
        """Stop serving, close the listener, release what it owns. Idempotent."""
        if self._stopped:
            return
        self._stopped = True
        thread = self._serve_thread
        if (
            thread is not None
            and thread is not threading.current_thread()
            and thread.is_alive()
        ):
            try:
                self.shutdown()
            except Exception:
                pass
        try:
            self.server_close()
        except Exception:
            pass
        finally:
            self._close_owned()

    def _close_owned(self) -> None:
        """Release what this listener owns (a session, a token). Default: none."""