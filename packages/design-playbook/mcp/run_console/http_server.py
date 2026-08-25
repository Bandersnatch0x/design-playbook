"""On-demand loopback HTTP server for the single-run read API (RCV1-006).

One process-owned server instance serves exactly one selected run over
one IP-literal loopback listener on an ephemeral port. Every route
requires the session bearer token compared in constant time; the exact
Host/Origin policy is enforced before authentication; only GET/HEAD
exist, with matching HEAD bodies suppressed; every response carries the
restrictive header policy (CSP ``frame-ancestors 'none'``, nosniff,
no-store, no CORS); and every failure is one fixed, bounded JSON error
envelope that leaks no path, token, locator, or traceback (S24-S28,
S39-S41). The server performs no outbound network call of any kind.
"""
from __future__ import annotations

import http.server
import json
import re
import secrets
import socket
import socketserver
import threading
from urllib.parse import parse_qsl, urlsplit

from .contract import (
    SNAPSHOT_CONTRACT_INVALID,
    SNAPSHOT_VERSION,
    SnapshotContractError,
    validate_snapshot,
)
from .projection import (
    SOURCE_HASH_MISMATCH,
    SOURCE_LOCATOR_INVALID,
    SourceViewError,
)
from .request_security import (
    ACTION_PAYLOAD_INVALID,
    DEFAULT_BIND_HOST,
    ERROR_MESSAGES,
    METHOD_NOT_ALLOWED,
    ORIGIN_INVALID,
    REQUEST_TOO_LARGE,
    RETRYABLE_CODES,
    ROUTE_NOT_FOUND,
    SESSION_TOKEN_INVALID,
    SNAPSHOT_BUILD_FAILED,
    canonical_authority,
    canonical_origin,
    ensure_loopback_bind_host,
    expected_hash_is_well_formed,
    extract_bearer_token,
    host_header_is_valid,
    origin_header_is_valid,
    query_carries_auth_material,
    security_headers,
    token_is_valid,
)
from .session import (
    DEFAULT_EXCERPT_MAX_CHARS,
    RunConsoleSession,
    RunConsoleSessionError,
)
from .snapshot_builder import SnapshotBuildError

ROUTE_SNAPSHOT = "/api/v1/snapshot"
_SOURCES_PREFIX = "/api/v1/sources/"
ALLOWED_METHODS = "GET, HEAD"
MAX_REQUEST_BODY_BYTES = 65536

_LOCATOR_PATTERN = re.compile(r"^src_[A-Za-z0-9_-]{16,}$")
# Sentinel for a header present more than once: never a valid single value.
_DUPLICATED = object()

_STATUS_BY_CODE = {
    ACTION_PAYLOAD_INVALID: 400,
    SESSION_TOKEN_INVALID: 401,
    ORIGIN_INVALID: 403,
    SOURCE_LOCATOR_INVALID: 404,
    ROUTE_NOT_FOUND: 404,
    METHOD_NOT_ALLOWED: 405,
    SOURCE_HASH_MISMATCH: 409,
    REQUEST_TOO_LARGE: 413,
    SNAPSHOT_CONTRACT_INVALID: 422,
    SNAPSHOT_BUILD_FAILED: 500,
}


def _error_payload(code: str, message: str | None = None) -> dict:
    """The fixed v1 error envelope: schemaVersion plus four error members."""
    return {
        "schemaVersion": SNAPSHOT_VERSION,
        "error": {
            "code": code,
            "message": message
            if message is not None
            else ERROR_MESSAGES.get(code, "The request was rejected."),
            "requestId": "req_" + secrets.token_hex(8),
            "retryable": code in RETRYABLE_CODES,
        },
    }


class RunConsoleRequestHandler(http.server.BaseHTTPRequestHandler):
    """One request against the session: validate, authenticate, serve."""

    protocol_version = "HTTP/1.1"
    server_version = "RunConsole"
    sys_version = ""
    timeout = 15

    def version_string(self) -> str:
        return "RunConsole"

    def log_message(self, format: str, *args: object) -> None:
        """Never log: no URL, token, or locator may reach any log."""

    # -- dispatch ------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        self._dispatch()

    def do_HEAD(self) -> None:  # noqa: N802
        self._dispatch()

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch()

    def do_PUT(self) -> None:  # noqa: N802
        self._dispatch()

    def do_DELETE(self) -> None:  # noqa: N802
        self._dispatch()

    def do_PATCH(self) -> None:  # noqa: N802
        self._dispatch()

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._dispatch()

    def do_TRACE(self) -> None:  # noqa: N802
        self._dispatch()

    def send_error(self, code, message=None, explain=None) -> None:  # type: ignore[override]
        """Bounded JSON for every stdlib-initiated rejection.

        Replaces the default HTML error pages (bad request line, line too
        long, unsupported method, unsupported version) with the fixed
        envelope so no stdlib detail, method name, or path is echoed.
        """
        try:
            self.close_connection = True
            mapping = {
                400: (400, ACTION_PAYLOAD_INVALID),
                414: (413, REQUEST_TOO_LARGE),
                501: (405, METHOD_NOT_ALLOWED),
                505: (400, ACTION_PAYLOAD_INVALID),
            }
            status, error_code = mapping.get(code, (400, ACTION_PAYLOAD_INVALID))
            headers = {"Allow": ALLOWED_METHODS} if status == 405 else None
            self._send_json(
                status, _error_payload(error_code), close=True, extra_headers=headers
            )
        except Exception:
            self.close_connection = True

    def _dispatch(self) -> None:
        self._responded = False
        try:
            self._process()
        except Exception:
            if not self._responded:
                self._fail_closed()

    def _fail_closed(self) -> None:
        try:
            self._send_json(500, _error_payload(SNAPSHOT_BUILD_FAILED), close=True)
        except Exception:
            self.close_connection = True

    # -- policy pipeline -------------------------------------------------

    def _process(self) -> None:
        session = self.server.session
        rejection = self._request_size_code()
        if rejection is not None:
            self._send_error(rejection)
            return
        bind_host = self.server.bind_host
        port = self.server.server_port
        if not host_header_is_valid(
            self._single_header("Host"), bind_host=bind_host, port=port
        ):
            self._send_error(ORIGIN_INVALID)
            return
        read_only = self.command in ("GET", "HEAD")
        if not origin_header_is_valid(
            self._single_header("Origin"),
            bind_host=bind_host,
            port=port,
            read_only=read_only,
        ):
            self._send_error(ORIGIN_INVALID)
            return
        split = urlsplit(self.path)
        if query_carries_auth_material(split.query):
            self._send_error(SESSION_TOKEN_INVALID)
            return
        presented = extract_bearer_token(self._single_header("Authorization"))
        if not token_is_valid(session.token, presented):
            self._send_error(SESSION_TOKEN_INVALID)
            return
        self._drain_body()
        path = split.path
        if path == ROUTE_SNAPSHOT:
            if not read_only:
                self._send_error(
                    METHOD_NOT_ALLOWED, extra_headers={"Allow": ALLOWED_METHODS}
                )
                return
            if split.query:
                # The snapshot read accepts no request parameters.
                self._send_error(ACTION_PAYLOAD_INVALID)
                return
            self._serve_snapshot(session)
            return
        if path.startswith(_SOURCES_PREFIX):
            if not read_only:
                self._send_error(
                    METHOD_NOT_ALLOWED, extra_headers={"Allow": ALLOWED_METHODS}
                )
                return
            self._serve_source(session, path, split.query)
            return
        self._send_error(ROUTE_NOT_FOUND)

    def _single_header(self, name: str) -> object:
        """One header value, ``None`` when absent, sentinel when duplicated."""
        values = self.headers.get_all(name)
        if not values:
            return None
        if len(values) > 1:
            return _DUPLICATED
        return values[0]

    def _request_size_code(self) -> str | None:
        """Bounded-body rejection before any body byte is read (S28)."""
        if self.headers.get_all("Transfer-Encoding"):
            return REQUEST_TOO_LARGE
        values = self.headers.get_all("Content-Length")
        if not values:
            return None
        if len(values) > 1:
            return ACTION_PAYLOAD_INVALID
        try:
            length = int(values[0].strip())
        except ValueError:
            return ACTION_PAYLOAD_INVALID
        if length < 0:
            return ACTION_PAYLOAD_INVALID
        if length > MAX_REQUEST_BODY_BYTES:
            return REQUEST_TOO_LARGE
        return None

    def _drain_body(self) -> None:
        """Discard an in-bound (already size-checked) body for keep-alive."""
        values = self.headers.get_all("Content-Length")
        if not values:
            return
        try:
            remaining = min(int(values[0]), MAX_REQUEST_BODY_BYTES)
        except ValueError:
            return
        while remaining > 0:
            chunk = self.rfile.read(min(remaining, 65536))
            if not chunk:
                self.close_connection = True
                return
            remaining -= len(chunk)

    # -- routes ---------------------------------------------------------

    def _serve_snapshot(self, session: RunConsoleSession) -> None:
        try:
            document = session.build_snapshot()
        except RunConsoleSessionError:
            # A closed session presents no valid token.
            self._send_error(SESSION_TOKEN_INVALID)
            return
        except SnapshotBuildError:
            # Never serve a previous snapshot as current.
            self._send_error(SNAPSHOT_BUILD_FAILED)
            return
        try:
            validate_snapshot(document)
        except SnapshotContractError as exc:
            self._send_error(SNAPSHOT_CONTRACT_INVALID, message=str(exc))
            return
        self._send_json(200, document)

    def _serve_source(self, session: RunConsoleSession, path: str, query: str) -> None:
        locator = path[len(_SOURCES_PREFIX):]
        if _LOCATOR_PATTERN.fullmatch(locator) is None:
            # Unknown, malformed, traversal, or encoded: uniform rejection.
            self._send_error(SOURCE_LOCATOR_INVALID)
            return
        params = parse_qsl(query, keep_blank_values=True)
        if len(params) != 1 or params[0][0] != "expectedHash":
            self._send_error(ACTION_PAYLOAD_INVALID)
            return
        expected_hash = params[0][1]
        if not expected_hash_is_well_formed(expected_hash):
            self._send_error(ACTION_PAYLOAD_INVALID)
            return
        try:
            view = session.resolve_source(locator)
        except RunConsoleSessionError:
            self._send_error(SESSION_TOKEN_INVALID)
            return
        except SourceViewError as exc:
            self._send_error(exc.code, message=str(exc))
            return
        if view.excerpt.content_hash != expected_hash:
            self._send_error(SOURCE_HASH_MISMATCH)
            return
        payload = {
            "schemaVersion": SNAPSHOT_VERSION,
            "sourceRef": view.excerpt.source_ref,
            "sourceHash": view.excerpt.content_hash,
            "anchor": None
            if view.anchor is None
            else {"kind": "semantic", "label": view.anchor},
            "mediaType": "text/plain; charset=utf-8",
            "excerpt": view.excerpt.text,
            "truncated": len(view.excerpt.text) >= DEFAULT_EXCERPT_MAX_CHARS,
        }
        self._send_json(200, payload)

    # -- responses --------------------------------------------------------

    def _send_error(
        self, code: str, *, message: str | None = None, extra_headers=None
    ) -> None:
        status = _STATUS_BY_CODE.get(code, 400)
        self._send_json(
            status,
            _error_payload(code, message=message),
            close=True,
            extra_headers=extra_headers,
        )

    def _send_json(
        self, status: int, payload: object, *, close: bool = False, extra_headers=None
    ) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        for name, value in security_headers().items():
            self.send_header(name, value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if extra_headers:
            for name, value in extra_headers.items():
                self.send_header(name, value)
        if close:
            self.close_connection = True
            self.send_header("Connection", "close")
        self.end_headers()
        self._responded = True
        if self.command != "HEAD":
            self.wfile.write(body)


class RunConsoleHTTPServer(http.server.ThreadingHTTPServer):
    """One IP-literal loopback listener serving exactly one session."""

    daemon_threads = True
    allow_reuse_address = False

    def __init__(
        self,
        session: RunConsoleSession,
        *,
        bind_host: str = DEFAULT_BIND_HOST,
        port: int = 0,
    ) -> None:
        if not isinstance(session, RunConsoleSession):
            raise TypeError("session must be a RunConsoleSession")
        host = ensure_loopback_bind_host(bind_host)
        if host == "::1":
            self.address_family = socket.AF_INET6
        super().__init__((host, port), RunConsoleRequestHandler)
        self.session = session
        self.bind_host = host
        bound_host, bound_port = self.socket.getsockname()[:2]
        if bound_host != host:
            self.server_close()
            raise OSError("socket did not bind to the requested loopback literal")
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

    def start_serving(self, poll_interval: float = 0.05) -> "RunConsoleHTTPServer":
        """Serve forever on a daemon thread."""
        if self._serve_thread is not None and self._serve_thread.is_alive():
            return self
        self._serve_thread = threading.Thread(
            target=self.serve_forever,
            kwargs={"poll_interval": poll_interval},
            daemon=True,
            name="run-console-server",
        )
        self._serve_thread.start()
        return self

    def stop(self) -> None:
        """Stop serving, close the listener, and invalidate the session.

        Idempotent; safe to call from any thread. Closing invalidates the
        token and every locator even for in-flight requests.
        """
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
            self.session.close()


def serve_run_console(
    session: RunConsoleSession,
    *,
    bind_host: str = DEFAULT_BIND_HOST,
    port: int = 0,
) -> RunConsoleHTTPServer:
    """Bind one loopback listener for the session and start serving."""
    server = RunConsoleHTTPServer(
        session, bind_host=bind_host, port=port
    )
    server.start_serving()
    return server
