"""Shared loopback listener rules for the plugin's own HTTP surfaces.

The run console and the preview review server both bind an IP-literal
loopback socket, and both need the same two rules: bind without a reverse-DNS
lookup, and tear a connection down with a half-close and drain so a client
body left unread never turns close into a TCP reset on Windows (ADR-0046).

Port policy and session ownership stay with each server: those are lifecycle
facts, not binding rules.
"""
from __future__ import annotations

import socket
import socketserver


def finish_gracefully(connection: socket.socket) -> None:
    """Half-close, drain the peer's remaining bytes, then let close happen."""
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


def bind_without_dns(server: socketserver.BaseServer) -> None:
    """Bind the socket and name it from getsockname, never via getfqdn.

    ``TCPServer.server_bind`` resolves the peer name with ``socket.getfqdn``;
    for a loopback literal there is nothing to resolve, and a slow or absent
    resolver must not sit in the bind path.
    """
    socketserver.TCPServer.server_bind(server)
    host, port = server.socket.getsockname()[:2]
    server.server_name = host
    server.server_port = port