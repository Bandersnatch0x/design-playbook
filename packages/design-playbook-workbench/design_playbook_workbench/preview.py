"""The isolated preview origin for imported carriers (R03).

Imported pages are untrusted content. They are served from a *separate*
loopback listener that has no session credential, no management API, and
no outbound network: the content-security policy denies connections,
denies form submission, and applies a sandbox so the document never shares
an origin with the workbench itself. A script in a previewed page can
therefore run (only when the maintainer explicitly enabled dynamic
preview) while still being unable to reach the parent window, the
management API, or the internet.
"""
from __future__ import annotations

import http.server
import json
import socket
import socketserver
import threading
from urllib.parse import parse_qsl, urlsplit

from .blobs import BlobStore
from .errors import WorkbenchError
from .security import (
    DEFAULT_BIND_HOST,
    canonical_authority,
    canonical_origin,
    ensure_loopback_bind_host,
    security_headers,
)

PREVIEW_PATH_PREFIX = "/p/"
MODES = ("static", "dynamic")

#: Content types a preview may declare; anything else falls back to text.
ALLOWED_MEDIA_TYPES = frozenset(
    {
        "text/html",
        "text/plain",
        "text/markdown",
        "text/css",
        "text/javascript",
        "text/typescript",
        "application/json",
        "application/yaml",
        "image/png",
        "image/jpeg",
        "image/webp",
        "image/gif",
        "image/svg+xml",
    }
)

def _frame_directive(frame_ancestors: tuple[str, ...]) -> str:
    """Only the declared management origin may frame a preview."""
    if frame_ancestors:
        return "frame-ancestors " + " ".join(frame_ancestors)
    return "frame-ancestors 'none'"


def _static_csp(frame_ancestors: tuple[str, ...]) -> str:
    return (
        "sandbox; default-src 'none'; script-src 'none'; connect-src 'none'; "
        "img-src data: blob:; style-src 'unsafe-inline'; font-src data:; "
        "media-src data:; object-src 'none'; base-uri 'none'; form-action 'none'; "
        + _frame_directive(frame_ancestors)
    )


def _dynamic_csp(frame_ancestors: tuple[str, ...]) -> str:
    # allow-scripts without allow-same-origin: the document runs its own
    # scripts in an opaque origin, cannot read the parent, and cannot call
    # the management API because no connection is permitted at all.
    return (
        "sandbox allow-scripts; default-src 'none'; "
        "script-src 'unsafe-inline' 'unsafe-eval'; connect-src 'none'; "
        "img-src data: blob:; style-src 'unsafe-inline'; font-src data:; "
        "media-src data:; object-src 'none'; base-uri 'none'; form-action 'none'; "
        + _frame_directive(frame_ancestors)
    )


_STATIC_CSP = _static_csp(())
_DYNAMIC_CSP = _dynamic_csp(())


class PreviewRequestHandler(http.server.BaseHTTPRequestHandler):
    """Serves exactly one shape: ``/p/<hash>/<mode>``."""

    protocol_version = "HTTP/1.1"
    server_version = "WorkbenchPreview"
    sys_version = ""
    timeout = 15

    def version_string(self) -> str:
        return "WorkbenchPreview"

    def log_message(self, format: str, *args: object) -> None:
        """Never log: no path or hash may reach any log."""

    def finish(self) -> None:
        super().finish()
        try:
            self.connection.shutdown(socket.SHUT_WR)
        except OSError:
            pass
        try:
            self.connection.settimeout(0.2)
            while self.connection.recv(65536):
                pass
        except OSError:
            pass

    def do_GET(self) -> None:  # noqa: N802
        self._serve()

    def do_HEAD(self) -> None:  # noqa: N802
        self._serve()

    def do_POST(self) -> None:  # noqa: N802
        # There is no write surface of any kind on the preview origin.
        self._reject(404, "route-not-found")

    def do_PUT(self) -> None:  # noqa: N802
        self._reject(404, "route-not-found")

    def do_DELETE(self) -> None:  # noqa: N802
        self._reject(404, "route-not-found")

    def do_PATCH(self) -> None:  # noqa: N802
        self._reject(404, "route-not-found")

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._reject(404, "route-not-found")

    def _serve(self) -> None:
        self._responded = False
        try:
            split = urlsplit(self.path)
            segments = split.path.split("/")
            if (
                len(segments) != 4
                or segments[1] != "p"
                or not segments[2]
                or segments[3] not in MODES
            ):
                self._reject(404, "route-not-found")
                return
            content_hash, mode = segments[2], segments[3]
            params = dict(parse_qsl(split.query, keep_blank_values=True))
            media_type = params.get("type", "text/plain")
            if media_type not in ALLOWED_MEDIA_TYPES:
                media_type = "text/plain"
            try:
                body = self.server.blobs.read(content_hash)
            except WorkbenchError:
                self._reject(404, "corrupt-content")
                return
            self._send(body, media_type=media_type, mode=mode)
        except Exception:
            if not self._responded:
                self._reject(500, "internal-error")

    def _reject(self, status: int, code: str) -> None:
        body = json.dumps(
            {"error": {"code": code}}, separators=(",", ":")
        ).encode("utf-8")
        self.send_response(status)
        for name, value in security_headers().items():
            self.send_header(name, value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.close_connection = True
        self.send_header("Connection", "close")
        self.end_headers()
        self._responded = True
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send(self, body: bytes, *, media_type: str, mode: str) -> None:
        headers = security_headers()
        frame_ancestors = getattr(self.server, "frame_ancestors", ())
        headers["Content-Security-Policy"] = (
            _static_csp(frame_ancestors)
            if mode == "static"
            else _dynamic_csp(frame_ancestors)
        )
        # A preview never receives or sets credentials of any kind.
        headers["Cross-Origin-Resource-Policy"] = "same-origin"
        self.send_response(200)
        for name, value in headers.items():
            self.send_header(name, value)
        self.send_header("Content-Type", f"{media_type}; charset=utf-8"
                         if media_type.startswith("text/")
                         or media_type in ("application/json", "application/yaml", "image/svg+xml")
                         else media_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self._responded = True
        if self.command != "HEAD":
            self.wfile.write(body)


class PreviewServer(http.server.ThreadingHTTPServer):
    """One IP-literal loopback listener with no session and no API."""

    daemon_threads = True
    allow_reuse_address = False

    def __init__(
        self,
        blobs: BlobStore,
        *,
        bind_host: str = DEFAULT_BIND_HOST,
        port: int = 0,
        frame_ancestors: tuple[str, ...] = (),
    ) -> None:
        host = ensure_loopback_bind_host(bind_host)
        if host == "::1":
            self.address_family = socket.AF_INET6
        super().__init__((host, port), PreviewRequestHandler)
        self.blobs = blobs
        # Only the management origin may frame a preview; with no declared
        # ancestor the document may not be framed at all.
        self.frame_ancestors = tuple(frame_ancestors)
        self.bind_host = host
        bound_host, bound_port = self.socket.getsockname()[:2]
        if bound_host != host:
            self.server_close()
            raise OSError("preview socket did not bind to the requested loopback literal")
        self.authority = canonical_authority(host, bound_port)
        self.origin = canonical_origin(host, bound_port)
        self._thread: threading.Thread | None = None

    def server_bind(self) -> None:
        socketserver.TCPServer.server_bind(self)
        host, port = self.socket.getsockname()[:2]
        self.server_name = host
        self.server_port = port

    @property
    def port(self) -> int:
        return self.socket.getsockname()[1]

    def start_serving(self, poll_interval: float = 0.05) -> "PreviewServer":
        if self._thread is not None and self._thread.is_alive():
            return self
        self._thread = threading.Thread(
            target=self.serve_forever,
            kwargs={"poll_interval": poll_interval},
            daemon=True,
            name="workbench-preview",
        )
        self._thread.start()
        return self

    def stop(self) -> None:
        thread = self._thread
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


def preview_media_type(entry_media_type: object) -> str:
    """The preview content type for one manifest entry (allowlisted)."""
    if isinstance(entry_media_type, str) and entry_media_type in ALLOWED_MEDIA_TYPES:
        return entry_media_type
    return "text/plain"
