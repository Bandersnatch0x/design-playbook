#!/usr/bin/env python3
"""RCV1-006 slice 3: the secured loopback read-API server (RED first).

Starts real servers bound to IP-literal loopback addresses on ephemeral
ports and drives them with http.client and raw sockets. Pins S24-S28 and
S39-S41 at the HTTP boundary: one loopback listener, exact Host/Origin
policy, bearer-token authentication compared in constant time, GET/HEAD
routes with matching HEAD and byte-for-byte zero side effects on the run
tree, the fixed header/error policy with no CORS and no leaks, bounded
request bodies, second-run isolation, close-time invalidation, and the
one-line CLI launcher.
"""
from __future__ import annotations

import contextlib
import hashlib
import http.client
import io
import json
import re
import socket
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

_PKG_ROOT = Path(__file__).resolve().parents[2]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from design_playbook.mcp.run_console.contract import validate_snapshot  # noqa: E402
from design_playbook.mcp.run_console.http_server import (  # noqa: E402
    MAX_REQUEST_BODY_BYTES,
    RunConsoleHTTPServer,
    serve_run_console,
)
from design_playbook.mcp.run_console.projection import (  # noqa: E402
    SOURCE_HASH_MISMATCH,
    SOURCE_LOCATOR_INVALID,
)
from design_playbook.mcp.run_console.request_security import (  # noqa: E402
    ACTION_PAYLOAD_INVALID,
    METHOD_NOT_ALLOWED,
    ORIGIN_INVALID,
    REQUEST_TOO_LARGE,
    ROUTE_NOT_FOUND,
    SESSION_TOKEN_INVALID,
    SNAPSHOT_BUILD_FAILED,
)
from design_playbook.mcp.run_console.session import (  # noqa: E402
    SESSION_CLOSED,
    RunConsoleSession,
    RunConsoleSessionError,
)
from design_playbook.mcp.run_console.snapshot_builder import (  # noqa: E402
    SnapshotBuildError,
    build_snapshot,
)
from design_playbook.scripts import run_console as run_console_cli  # noqa: E402

_FIXTURES = Path(__file__).resolve().parent / "fixtures"
_NOW = "2026-08-25T10:00:00Z"
_LATER = "2026-08-25T10:20:00Z"
_REQUEST_ID = re.compile(r"^req_[A-Za-z0-9_-]{4,64}$")
_CLI_LINE = re.compile(
    r"^Run console: (http://127\.0\.0\.1:\d+) token: ([A-Za-z0-9_-]{43,})$"
)

_TOKEN = object()
_HOST = object()
_ORIGIN = object()

_CONTRACT_BIND = {
    "ok": True,
    "schemaVersion": 1,
    "contract_sha": "a" * 64,
    "decision_log_sha": "b" * 64,
    "open_fields": [],
    "assumed_fields": [],
    "stale_fields": [],
    "blockers": [],
}
_MANIFEST_ENTRY = {
    "criterion": "L6.3",
    "artifact": "L6.3-error.png",
    "ts": "2026-08-25T09:00:00+08:00",
}
_HTML_ARTIFACT = (_FIXTURES / "evidence-artifact.html").read_bytes()


class _Clock:
    def __init__(self, now: str) -> None:
        self.now = now

    def __call__(self) -> str:
        return self.now


def _write(root: Path, relpath: str, text: str) -> None:
    target = root / relpath
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def _make_root(base: Path, name: str = "run-a", *, artifact: bytes = _HTML_ARTIFACT) -> Path:
    root = base / name
    root.mkdir(parents=True)
    _write(root, "spec.md", (_FIXTURES / "spec-script-summary.md").read_text(encoding="utf-8"))
    _write(root, "plan.md", (_FIXTURES / "plan-profile.md").read_text(encoding="utf-8"))
    _write(root, "point-back.md", (_FIXTURES / "point-back-pass-closed.md").read_text(encoding="utf-8"))
    _write(root, "contract-bind.json", json.dumps(_CONTRACT_BIND))
    _write(root, "evidence/manifest.jsonl", json.dumps(_MANIFEST_ENTRY) + "\n")
    (root / "evidence" / "L6.3-error.png").write_bytes(artifact)
    (root / "preview").mkdir()
    return root


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(str(path.relative_to(root)).replace("\\", "/").encode("utf-8"))
        digest.update(b"\x00")
        digest.update(path.read_bytes())
        digest.update(b"\x00")
    return digest.hexdigest()


def _record(document: dict, source_ref: str) -> dict:
    for item in document["sources"]["items"]:
        if item["sourceRef"] == source_ref:
            return item
    raise AssertionError(f"missing source record {source_ref}")


def _artifact_record(document: dict) -> dict:
    for item in document["sources"]["items"]:
        if item["sourceRef"].startswith("source.evidence-artifact.") and item["locator"]:
            return item
    raise AssertionError("no artifact record with a locator")


def _assert_error(payload: bytes, code: str) -> None:
    envelope = json.loads(payload)
    assert isinstance(envelope, dict)
    assert set(envelope) == {"schemaVersion", "error"}, set(envelope)
    assert envelope["schemaVersion"] == 1
    error = envelope["error"]
    assert set(error) == {"code", "message", "requestId", "retryable"}, set(error)
    assert error["code"] == code, error
    assert _REQUEST_ID.match(error["requestId"]), error
    assert isinstance(error["retryable"], bool)


def _fetch(server, token: str, method: str, path: str, *, origin: str | None = None, host: str | None = None):
    conn = http.client.HTTPConnection(server.bind_host, server.port, timeout=10)
    try:
        conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        conn.putheader("Host", host or server.authority)
        if origin is not None:
            conn.putheader("Origin", origin)
        conn.putheader("Authorization", f"Bearer {token}")
        conn.endheaders()
        response = conn.getresponse()
        payload = response.read()
        fields = {k.lower(): v for k, v in response.getheaders()}
        return response.status, fields, payload
    finally:
        conn.close()


class _ServerTestCase(unittest.TestCase):
    """One real server on 127.0.0.1 with an ephemeral port per test."""

    bind_host = "127.0.0.1"

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name).resolve()
        self.run_root = _make_root(self.base)
        self.clock = _Clock(_NOW)
        self.session = RunConsoleSession(
            run_root=self.run_root, package_root=_PKG_ROOT, now_fn=self.clock
        )
        self.server = serve_run_console(self.session, bind_host=self.bind_host, port=0)
        self.addCleanup(self.server.stop)
        self.token = self.session.token

    # -- request helpers ------------------------------------------------

    def _api(self, method, path, *, token=_TOKEN, host=_HOST, origin=_ORIGIN, headers=None, body=None):
        conn = http.client.HTTPConnection(self.server.bind_host, self.server.port, timeout=10)
        try:
            conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
            if host is _HOST:
                conn.putheader("Host", self.server.authority)
            elif host is not None:
                conn.putheader("Host", host)
            if origin is not _ORIGIN:
                conn.putheader("Origin", origin)
            if token is _TOKEN:
                conn.putheader("Authorization", f"Bearer {self.token}")
            elif token is not None:
                conn.putheader("Authorization", f"Bearer {token}")
            for name, value in (headers or {}).items():
                conn.putheader(name, value)
            conn.endheaders(body)
            response = conn.getresponse()
            payload = response.read()
            fields = {k.lower(): v for k, v in response.getheaders()}
            return response.status, fields, payload
        finally:
            conn.close()

    def _raw(self, data: bytes, *, timeout: float = 5.0):
        with socket.create_connection(
            (self.server.bind_host, self.server.port), timeout=timeout
        ) as sock:
            sock.sendall(data)
            chunks = []
            while True:
                try:
                    chunk = sock.recv(65536)
                except socket.timeout:
                    break
                if not chunk:
                    break
                chunks.append(chunk)
        raw = b"".join(chunks)
        self.assertTrue(raw.startswith(b"HTTP/1.1 "), raw[:40])
        return int(raw.split(b" ", 2)[1]), raw

    def _snapshot_document(self) -> dict:
        status, _, payload = self._api("GET", "/api/v1/snapshot")
        self.assertEqual(status, 200)
        return json.loads(payload)

    def _source_url(self, source_ref: str = "source.specification") -> str:
        record = _record(self._snapshot_document(), source_ref)
        self.assertIsNotNone(record["locator"])
        return f"/api/v1/sources/{record['locator']}?expectedHash={record['observedHash']}"


class ReadApiTest(_ServerTestCase):
    """S20/S27: the two read routes and matching HEAD."""

    def test_get_snapshot_serves_contract_valid_document(self) -> None:
        status, headers, payload = self._api("GET", "/api/v1/snapshot")
        self.assertEqual(status, 200)
        self.assertEqual(headers["content-type"], "application/json; charset=utf-8")
        document = json.loads(payload)
        self.assertEqual(validate_snapshot(document), document)
        self.assertEqual(document["schemaVersion"], 1)

    def test_security_headers_on_success_and_no_cors(self) -> None:
        status, headers, _ = self._api("GET", "/api/v1/snapshot")
        self.assertEqual(status, 200)
        self.assertIn("frame-ancestors 'none'", headers["content-security-policy"])
        self.assertIn("default-src 'none'", headers["content-security-policy"])
        self.assertEqual(headers["x-content-type-options"], "nosniff")
        self.assertEqual(headers["cache-control"], "no-store")
        for name in headers:
            self.assertFalse(name.startswith("access-control-"), name)

    def test_snapshot_is_stable_across_requests(self) -> None:
        _, _, first = self._api("GET", "/api/v1/snapshot")
        _, _, second = self._api("GET", "/api/v1/snapshot")
        self.assertEqual(first, second)

    def test_head_snapshot_matches_get_without_body(self) -> None:
        get_status, get_headers, get_payload = self._api("GET", "/api/v1/snapshot")
        head_status, head_headers, head_payload = self._api("HEAD", "/api/v1/snapshot")
        self.assertEqual(head_status, get_status)
        self.assertEqual(head_payload, b"")
        self.assertEqual(head_headers["content-length"], get_headers["content-length"])
        self.assertEqual(head_headers["content-type"], get_headers["content-type"])
        self.assertEqual(
            head_headers["content-security-policy"],
            get_headers["content-security-policy"],
        )
        self.assertEqual(head_headers["cache-control"], "no-store")

    def test_get_source_returns_bounded_excerpt_payload(self) -> None:
        document = self._snapshot_document()
        record = _record(document, "source.specification")
        status, _, payload = self._api(
            "GET",
            f"/api/v1/sources/{record['locator']}?expectedHash={record['observedHash']}",
        )
        self.assertEqual(status, 200)
        view = json.loads(payload)
        self.assertEqual(view["schemaVersion"], 1)
        self.assertEqual(view["sourceRef"], "source.specification")
        self.assertEqual(view["sourceHash"], record["observedHash"])
        self.assertIsNone(view["anchor"])
        self.assertEqual(view["mediaType"], "text/plain; charset=utf-8")
        self.assertTrue(view["excerpt"])
        self.assertFalse(view["truncated"])

    def test_head_source_matches_get_without_body(self) -> None:
        url = self._source_url()
        get_status, get_headers, _ = self._api("GET", url)
        head_status, head_headers, head_payload = self._api("HEAD", url)
        self.assertEqual(head_status, 200)
        self.assertEqual(head_payload, b"")
        self.assertEqual(head_headers["content-length"], get_headers["content-length"])
        self.assertEqual(head_headers["content-type"], "application/json; charset=utf-8")

    def test_source_excerpt_escapes_html_artifact_content(self) -> None:
        record = _artifact_record(self._snapshot_document())
        status, _, payload = self._api(
            "GET",
            f"/api/v1/sources/{record['locator']}?expectedHash={record['observedHash']}",
        )
        self.assertEqual(status, 200)
        self.assertNotIn(b"<script", payload)
        self.assertNotIn(b"<html", payload)
        self.assertIn("&lt;", json.loads(payload)["excerpt"])

    def test_small_get_body_is_accepted_and_drained(self) -> None:
        status, _, _ = self._api("GET", "/api/v1/snapshot", body=b"abc")
        self.assertEqual(status, 200)


class ExcerptBoundTest(unittest.TestCase):
    def test_long_artifact_excerpt_is_truncated_at_the_fixed_bound(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _make_root(Path(tmp).resolve(), artifact=b"A" * 10000)
            session = RunConsoleSession(
                run_root=root, package_root=_PKG_ROOT, now_fn=_Clock(_NOW)
            )
            server = serve_run_console(session, bind_host="127.0.0.1", port=0)
            self.addCleanup(server.stop)
            status, _, payload = _fetch(
                server, session.token, "GET", "/api/v1/snapshot"
            )
            self.assertEqual(status, 200)
            record = _artifact_record(json.loads(payload))
            status, _, payload = _fetch(
                server,
                session.token,
                "GET",
                f"/api/v1/sources/{record['locator']}?expectedHash={record['observedHash']}",
            )
            self.assertEqual(status, 200)
            view = json.loads(payload)
            self.assertTrue(view["truncated"])
            self.assertEqual(len(view["excerpt"]), 4000)
            self.assertEqual(view["excerpt"], "A" * 4000)


class AuthenticationTest(_ServerTestCase):
    """S25: token presentation rules."""

    def test_missing_token_is_rejected(self) -> None:
        status, _, payload = self._api("GET", "/api/v1/snapshot", token=None)
        self.assertEqual(status, 401)
        _assert_error(payload, SESSION_TOKEN_INVALID)

    def test_wrong_token_is_rejected(self) -> None:
        status, _, payload = self._api("GET", "/api/v1/snapshot", token="w" * 43)
        self.assertEqual(status, 401)
        _assert_error(payload, SESSION_TOKEN_INVALID)

    def test_malformed_authorization_headers_are_rejected(self) -> None:
        token = "a" * 43
        for header in (
            "Bearer",
            f"bearer {token}",
            f"Basic {token}",
            f"Bearer  {token}",
            "Bearer short",
            "",
        ):
            with self.subTest(header=header):
                status, _, payload = self._api(
                    "GET", "/api/v1/snapshot", token=None, headers={"Authorization": header}
                )
                self.assertEqual(status, 401)
                self.assertEqual(
                    json.loads(payload)["error"]["code"], SESSION_TOKEN_INVALID
                )

    def test_token_in_query_string_is_never_accepted(self) -> None:
        status, _, payload = self._api(
            "GET", f"/api/v1/snapshot?token={self.token}", token=None
        )
        self.assertEqual(status, 401)
        self.assertEqual(json.loads(payload)["error"]["code"], SESSION_TOKEN_INVALID)
        status, _, payload = self._api(
            "GET", f"/api/v1/snapshot?access_token={self.token}"
        )
        self.assertEqual(status, 401)
        self.assertEqual(json.loads(payload)["error"]["code"], SESSION_TOKEN_INVALID)

    def test_duplicate_authorization_headers_are_rejected(self) -> None:
        request = (
            f"GET /api/v1/snapshot HTTP/1.1\r\n"
            f"Host: {self.server.authority}\r\n"
            f"Authorization: Bearer {self.token}\r\n"
            f"Authorization: Bearer {self.token}\r\n"
            f"Connection: close\r\n\r\n"
        ).encode()
        status, _ = self._raw(request)
        self.assertEqual(status, 401)

    def test_reused_token_after_close_is_invalid(self) -> None:
        stale = self.token
        self.server.stop()
        session = RunConsoleSession(
            run_root=self.run_root, package_root=_PKG_ROOT, now_fn=self.clock
        )
        server = serve_run_console(session, bind_host="127.0.0.1", port=0)
        self.addCleanup(server.stop)
        status, _, payload = _fetch(server, stale, "GET", "/api/v1/snapshot")
        self.assertEqual(status, 401)
        _assert_error(payload, SESSION_TOKEN_INVALID)
        status, _, payload = _fetch(server, session.token, "GET", "/api/v1/snapshot")
        self.assertEqual(status, 200)

    def test_expired_locator_is_rejected(self) -> None:
        record = _record(self._snapshot_document(), "source.specification")
        self.clock.now = _LATER
        status, _, payload = self._api(
            "GET",
            f"/api/v1/sources/{record['locator']}?expectedHash={record['observedHash']}",
        )
        self.assertEqual(status, 404)
        _assert_error(payload, SOURCE_LOCATOR_INVALID)

    def test_source_hash_mismatch_is_409_and_retryable(self) -> None:
        record = _record(self._snapshot_document(), "source.specification")
        wrong = "sha256:" + "b" * 64
        status, _, payload = self._api(
            "GET", f"/api/v1/sources/{record['locator']}?expectedHash={wrong}"
        )
        self.assertEqual(status, 409)
        envelope = json.loads(payload)
        self.assertEqual(envelope["error"]["code"], SOURCE_HASH_MISMATCH)
        self.assertTrue(envelope["error"]["retryable"])


class HostOriginTest(_ServerTestCase):
    """S26: exact Host and Origin rules."""

    def test_host_mismatches_are_rejected(self) -> None:
        port = self.server.port
        for host in (
            f"localhost:{port}",
            "127.0.0.1",
            "127.0.0.1:1",
            f"127.0.0.2:{port}",
            f"http://127.0.0.1:{port}",
            f"[::1]:{port}",
            f"evil.example:{port}",
            "",
            f"127.0.0.1:{port}/",
        ):
            with self.subTest(host=host):
                status, _, payload = self._api("GET", "/api/v1/snapshot", host=host)
                self.assertEqual(status, 403)
                _assert_error(payload, ORIGIN_INVALID)

    def test_missing_host_header_is_rejected(self) -> None:
        status, _, payload = self._api("GET", "/api/v1/snapshot", host=None)
        self.assertEqual(status, 403)
        _assert_error(payload, ORIGIN_INVALID)

    def test_duplicate_host_headers_are_rejected(self) -> None:
        request = (
            f"GET /api/v1/snapshot HTTP/1.1\r\n"
            f"Host: {self.server.authority}\r\n"
            f"Host: evil.example:{self.server.port}\r\n"
            f"Authorization: Bearer {self.token}\r\n"
            f"Connection: close\r\n\r\n"
        ).encode()
        status, _ = self._raw(request)
        self.assertEqual(status, 403)

    def test_conflicting_get_origins_are_rejected(self) -> None:
        port = self.server.port
        for origin in (
            "null",
            f"http://localhost:{port}",
            f"https://127.0.0.1:{port}",
            "http://127.0.0.1:1",
            f"http://127.0.0.2:{port}",
            f"http://127.0.0.1:{port}/",
            "file://127.0.0.1",
            "moz-extension://0123456789abcdef",
        ):
            with self.subTest(origin=origin):
                status, _, payload = self._api("GET", "/api/v1/snapshot", origin=origin)
                self.assertEqual(status, 403)
                _assert_error(payload, ORIGIN_INVALID)

    def test_absent_and_exact_origins_are_accepted_for_reads(self) -> None:
        status, _, _ = self._api("GET", "/api/v1/snapshot")
        self.assertEqual(status, 200)
        status, _, _ = self._api("GET", "/api/v1/snapshot", origin=self.server.origin)
        self.assertEqual(status, 200)

    def test_non_read_methods_require_the_exact_origin(self) -> None:
        status, _, payload = self._api("POST", "/api/v1/snapshot")
        self.assertEqual(status, 403)
        _assert_error(payload, ORIGIN_INVALID)
        status, _, payload = self._api("POST", "/api/v1/snapshot", origin="http://evil.example")
        self.assertEqual(status, 403)
        status, headers, payload = self._api(
            "POST", "/api/v1/snapshot", origin=self.server.origin
        )
        self.assertEqual(status, 405)
        self.assertEqual(headers["allow"], "GET, HEAD")


class MethodAndRouteTest(_ServerTestCase):
    """S28/S39: the exact route and method contract."""

    def test_write_methods_on_snapshot_route_are_405_with_accurate_allow(self) -> None:
        for method in ("POST", "PUT", "DELETE", "PATCH", "OPTIONS", "TRACE"):
            with self.subTest(method=method):
                status, headers, payload = self._api(
                    method, "/api/v1/snapshot", origin=self.server.origin
                )
                self.assertEqual(status, 405)
                self.assertEqual(headers["allow"], "GET, HEAD")
                _assert_error(payload, METHOD_NOT_ALLOWED)

    def test_write_methods_on_source_route_are_405_with_accurate_allow(self) -> None:
        url = self._source_url()
        for method in ("POST", "OPTIONS", "TRACE"):
            with self.subTest(method=method):
                status, headers, payload = self._api(
                    method, url, origin=self.server.origin
                )
                self.assertEqual(status, 405)
                self.assertEqual(headers["allow"], "GET, HEAD")
                _assert_error(payload, METHOD_NOT_ALLOWED)

    def test_unknown_routes_are_404_with_bounded_errors(self) -> None:
        for path in (
            "/",
            "/favicon.ico",
            "/api",
            "/api/v1",
            "/api/v1/nope",
            "/api/v1/snapshot/",
            "/api/v1/snapshot/x",
            "/api/v1/actions/refresh",
            "/api/v1/sources",
        ):
            with self.subTest(path=path):
                status, _, payload = self._api("GET", path)
                self.assertEqual(status, 404)
                _assert_error(payload, ROUTE_NOT_FOUND)

    def test_post_refresh_action_does_not_exist(self) -> None:
        status, _, payload = self._api(
            "POST",
            "/api/v1/actions/refresh",
            origin=self.server.origin,
            headers={"Content-Type": "application/json"},
            body=json.dumps({"schemaVersion": 1, "action": "refresh"}).encode(),
        )
        self.assertEqual(status, 404)
        _assert_error(payload, ROUTE_NOT_FOUND)

    def test_malformed_locators_are_404_locator_invalid(self) -> None:
        good_hash = "sha256:" + "a" * 64
        for locator in (
            "not-a-locator",
            "src_short",
            "src_" + "a" * 300,
            "src_" + "a" * 24 + "!",
            "..%2f..%2fetc%2fpasswd",
            "src_..%5c..%5cwin.ini",
            "src_abcd/extra",
            "src_%00",
        ):
            with self.subTest(locator=locator):
                status, _, payload = self._api(
                    "GET", f"/api/v1/sources/{locator}?expectedHash={good_hash}"
                )
                self.assertEqual(status, 404)
                _assert_error(payload, SOURCE_LOCATOR_INVALID)

    def test_snapshot_rejects_query_parameters(self) -> None:
        status, _, payload = self._api("GET", "/api/v1/snapshot?x=1")
        self.assertEqual(status, 400)
        _assert_error(payload, ACTION_PAYLOAD_INVALID)

    def test_source_requires_exactly_one_well_formed_expected_hash(self) -> None:
        url = self._source_url()
        locator = url.split("?", 1)[0].rsplit("/", 1)[1]
        good_hash = "sha256:" + "a" * 64
        for path in (
            f"/api/v1/sources/{locator}",
            f"/api/v1/sources/{locator}?expectedHash=",
            f"/api/v1/sources/{locator}?expectedHash=sha256:abc",
            f"/api/v1/sources/{locator}?expectedHash={good_hash}&x=1",
            f"/api/v1/sources/{locator}?x={good_hash}",
            f"/api/v1/sources/{locator}?expectedHash={good_hash}&expectedHash={good_hash}",
        ):
            with self.subTest(path=path):
                status, _, payload = self._api("GET", path)
                self.assertEqual(status, 400)
                _assert_error(payload, ACTION_PAYLOAD_INVALID)

    def test_unknown_http_verb_is_rejected_bounded(self) -> None:
        request = (
            f"PROPFIND /api/v1/snapshot HTTP/1.1\r\n"
            f"Host: {self.server.authority}\r\n"
            f"Authorization: Bearer {self.token}\r\n"
            f"Connection: close\r\n\r\n"
        ).encode()
        status, raw = self._raw(request)
        self.assertEqual(status, 405)
        self.assertIn(b"Allow: GET, HEAD", raw)
        self.assertNotIn(b"PROPFIND", raw.split(b"\r\n\r\n", 1)[1])


class RequestBodyTest(_ServerTestCase):
    """S28: bounded request bodies."""

    def test_oversized_content_length_is_rejected_before_reading(self) -> None:
        request = (
            f"POST /api/v1/snapshot HTTP/1.1\r\n"
            f"Host: {self.server.authority}\r\n"
            f"Origin: {self.server.origin}\r\n"
            f"Authorization: Bearer {self.token}\r\n"
            f"Content-Length: 100000000\r\n"
            f"Connection: close\r\n\r\n"
        ).encode()
        status, raw = self._raw(request)
        self.assertEqual(status, 413)
        self.assertIn(REQUEST_TOO_LARGE.encode(), raw)

    def test_body_over_the_bound_is_rejected(self) -> None:
        request = (
            f"POST /api/v1/snapshot HTTP/1.1\r\n"
            f"Host: {self.server.authority}\r\n"
            f"Origin: {self.server.origin}\r\n"
            f"Authorization: Bearer {self.token}\r\n"
            f"Content-Length: {MAX_REQUEST_BODY_BYTES + 1}\r\n"
            f"Connection: close\r\n\r\n"
        ).encode()
        status, _ = self._raw(request)
        self.assertEqual(status, 413)

    def test_malformed_content_length_is_rejected(self) -> None:
        request = (
            f"GET /api/v1/snapshot HTTP/1.1\r\n"
            f"Host: {self.server.authority}\r\n"
            f"Authorization: Bearer {self.token}\r\n"
            f"Content-Length: abc\r\n"
            f"Connection: close\r\n\r\n"
        ).encode()
        status, _ = self._raw(request)
        self.assertEqual(status, 400)

    def test_duplicate_content_length_is_rejected(self) -> None:
        request = (
            f"GET /api/v1/snapshot HTTP/1.1\r\n"
            f"Host: {self.server.authority}\r\n"
            f"Authorization: Bearer {self.token}\r\n"
            f"Content-Length: 1\r\n"
            f"Content-Length: 2\r\n"
            f"Connection: close\r\n\r\nx"
        ).encode()
        status, _ = self._raw(request)
        self.assertEqual(status, 400)

    def test_chunked_transfer_encoding_is_rejected(self) -> None:
        request = (
            f"POST /api/v1/snapshot HTTP/1.1\r\n"
            f"Host: {self.server.authority}\r\n"
            f"Origin: {self.server.origin}\r\n"
            f"Authorization: Bearer {self.token}\r\n"
            f"Transfer-Encoding: chunked\r\n"
            f"Connection: close\r\n\r\n"
        ).encode()
        status, _ = self._raw(request)
        self.assertEqual(status, 413)


class LeakTest(_ServerTestCase):
    """Bounded errors; no token, path, or stack-trace leaks."""

    def _error_responses(self):
        return [
            self._api("GET", "/api/v1/snapshot", token=None),
            self._api("GET", "/api/v1/snapshot", host="evil.example:1"),
            self._api("GET", "/api/v1/snapshot", origin="http://evil.example"),
            self._api("GET", "/api/v1/nope"),
            self._api("POST", "/api/v1/snapshot", origin=self.server.origin),
            self._api(
                "GET", "/api/v1/sources/not-a-locator?expectedHash=sha256:" + "a" * 64
            ),
        ]

    def test_error_bodies_are_fixed_and_leak_free(self) -> None:
        for status, _, payload in self._error_responses():
            self.assertLess(status, 500)
            text = payload.decode("utf-8")
            self.assertNotIn(self.token, text)
            self.assertNotIn(str(self.run_root), text)
            self.assertNotIn(str(self.base), text)
            self.assertNotIn("Traceback", text)
            self.assertNotIn(".py", text)
            self.assertNotIn("run-a", text)
            _assert_error(payload, json.loads(payload)["error"]["code"])

    def test_error_responses_carry_the_full_header_policy(self) -> None:
        for status, headers, _ in self._error_responses():
            self.assertIn("frame-ancestors 'none'", headers["content-security-policy"])
            self.assertEqual(headers["x-content-type-options"], "nosniff")
            self.assertEqual(headers["cache-control"], "no-store")
            for name in headers:
                self.assertFalse(name.startswith("access-control-"), name)

    def test_token_never_appears_in_any_response(self) -> None:
        _, headers, payload = self._api("GET", "/api/v1/snapshot")
        _, headers2, payload2 = self._api("GET", self._source_url())
        for text in (payload.decode("utf-8"), payload2.decode("utf-8")):
            self.assertNotIn(self.token, text)
        for fields in (headers, headers2):
            for value in fields.values():
                self.assertNotIn(self.token, value)

    def test_server_header_is_bounded(self) -> None:
        _, headers, _ = self._api("GET", "/api/v1/snapshot")
        self.assertEqual(headers["server"], "RunConsole")

    def test_typed_build_failure_is_bounded_500(self) -> None:
        with mock.patch.object(
            self.session, "build_snapshot", side_effect=SnapshotBuildError("BUILD_FAILED")
        ):
            status, _, payload = self._api("GET", "/api/v1/snapshot")
        self.assertEqual(status, 500)
        _assert_error(payload, SNAPSHOT_BUILD_FAILED)

    def test_internal_failure_is_bounded_500(self) -> None:
        boom = RuntimeError("boom " + str(self.run_root))
        with mock.patch.object(self.session, "build_snapshot", side_effect=boom):
            status, _, payload = self._api("GET", "/api/v1/snapshot")
        self.assertEqual(status, 500)
        _assert_error(payload, SNAPSHOT_BUILD_FAILED)
        self.assertNotIn(b"boom", payload)


class RunIsolationTest(_ServerTestCase):
    """S41: only the selected run is served."""

    def test_second_run_locator_and_content_are_inaccessible(self) -> None:
        other_root = _make_root(
            self.base, "run-b", artifact=b"RUN-B-MARKER-006 " + b"z" * 64
        )
        other = build_snapshot(
            selected_root=other_root,
            package_root=_PKG_ROOT,
            session_secret=b"isolation-secret-006",
            now=_NOW,
        )
        record = _artifact_record(other.document)
        status, _, payload = self._api(
            "GET",
            f"/api/v1/sources/{record['locator']}?expectedHash={record['observedHash']}",
        )
        self.assertEqual(status, 404)
        _assert_error(payload, SOURCE_LOCATOR_INVALID)
        _, _, payload = self._api("GET", "/api/v1/snapshot")
        self.assertNotIn(b"RUN-B-MARKER-006", payload)


class ZeroSideEffectTest(_ServerTestCase):
    """S27: GET/HEAD leave the run tree byte-for-byte identical."""

    def test_full_read_battery_writes_nothing(self) -> None:
        before = _tree_digest(self.run_root)
        url = self._source_url()
        self._api("GET", "/api/v1/snapshot")
        self._api("HEAD", "/api/v1/snapshot")
        self._api("GET", url)
        self._api("HEAD", url)
        self._api("GET", "/api/v1/snapshot", token=None)
        self._api("GET", "/api/v1/snapshot", origin="http://evil.example")
        self._api("GET", "/api/v1/nope")
        self._api("POST", "/api/v1/snapshot", origin=self.server.origin)
        self._api("GET", "/api/v1/sources/not-a-locator?expectedHash=sha256:" + "a" * 64)
        self.assertEqual(_tree_digest(self.run_root), before)


class CloseTest(_ServerTestCase):
    """Close-time invalidation and the after-close race."""

    def test_requests_after_close_fail_cleanly(self) -> None:
        self.server.stop()
        self.assertTrue(self.session.closed)
        self.assertIsNone(self.session.token)
        with self.assertRaises(OSError):
            self._api("GET", "/api/v1/snapshot")
        with self.assertRaises(RunConsoleSessionError) as ctx:
            self.session.resolve_source("src_" + "a" * 24)
        self.assertEqual(ctx.exception.code, SESSION_CLOSED)

    def test_stop_is_idempotent(self) -> None:
        self.server.stop()
        self.server.stop()
        self.assertTrue(self.session.closed)


class BindPolicyTest(unittest.TestCase):
    """S24: one IP-literal loopback listener only."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name).resolve()
        self.run_root = _make_root(self.base)
        self.session = RunConsoleSession(
            run_root=self.run_root, package_root=_PKG_ROOT, now_fn=_Clock(_NOW)
        )
        self.addCleanup(self.session.close)

    def test_server_socket_is_one_loopback_listener(self) -> None:
        server = serve_run_console(self.session, bind_host="127.0.0.1", port=0)
        self.addCleanup(server.stop)
        host, port = server.socket.getsockname()[:2]
        self.assertEqual(host, "127.0.0.1")
        self.assertGreater(port, 0)
        self.assertLess(port, 65536)
        self.assertEqual(server.socket.family, socket.AF_INET)
        self.assertEqual(server.bind_host, "127.0.0.1")
        self.assertEqual(server.authority, f"127.0.0.1:{port}")
        self.assertEqual(server.origin, f"http://127.0.0.1:{port}")

    def test_ipv6_loopback_listener_serves_reads(self) -> None:
        try:
            server = serve_run_console(self.session, bind_host="::1", port=0)
        except OSError as exc:
            self.skipTest(f"no IPv6 loopback listener: {exc}")
        self.addCleanup(server.stop)
        host, port = server.socket.getsockname()[:2]
        self.assertEqual(host, "::1")
        self.assertEqual(server.socket.family, socket.AF_INET6)
        status, _, payload = _fetch(
            server, self.session.token, "GET", "/api/v1/snapshot", origin=server.origin
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(payload)["schemaVersion"], 1)

    def test_non_loopback_bind_hosts_are_rejected(self) -> None:
        for host in (
            "0.0.0.0",
            "localhost",
            "192.168.1.5",
            "::",
            "*",
            "",
            None,
            "127.0.0.2",
        ):
            with self.subTest(host=host):
                with self.assertRaises(ValueError):
                    RunConsoleHTTPServer(self.session, bind_host=host)
                with self.assertRaises(ValueError):
                    serve_run_console(self.session, bind_host=host)


class BoundaryScanTest(unittest.TestCase):
    """S40: no outbound-network, exec, or persistence primitive."""

    def test_no_outbound_network_or_exec_primitives(self) -> None:
        run_console_dir = Path(__file__).resolve().parent
        modules = [
            run_console_dir / "session.py",
            run_console_dir / "request_security.py",
            run_console_dir / "http_server.py",
            _PKG_ROOT / "scripts" / "run_console.py",
        ]
        banned = (
            "urlopen",
            "urllib.request",
            "import requests",
            "requests.get",
            "requests.post",
            "create_connection",
            "subprocess",
            "os.system",
            "eval(",
            "exec(",
            "socket.connect",
            "telemetry",
        )
        for path in modules:
            self.assertTrue(path.exists(), str(path))
            source = path.read_text(encoding="utf-8")
            for token in banned:
                self.assertNotIn(token, source, f"{path.name}: {token}")


class ConsoleCLITest(unittest.TestCase):
    """The one-line launcher: URL plus token, exactly once, on stdout."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name).resolve()
        self.run_root = _make_root(self.base)

    def test_cli_serves_one_run_and_prints_exactly_one_line(self) -> None:
        servers = []
        real_serve_forever = RunConsoleHTTPServer.serve_forever

        def wrapped(self, poll_interval=0.5):
            servers.append(self)
            real_serve_forever(self, poll_interval)

        out = io.StringIO()
        result: dict = {}

        def run() -> None:
            with contextlib.redirect_stdout(out):
                result["code"] = run_console_cli.main([str(self.run_root)])

        with mock.patch.object(RunConsoleHTTPServer, "serve_forever", wrapped):
            thread = threading.Thread(target=run, daemon=True)
            thread.start()
            line = None
            for _ in range(200):
                text = out.getvalue()
                if text.endswith("\n"):
                    line = text
                    break
                time.sleep(0.05)
            self.assertIsNotNone(line, out.getvalue())
            match = _CLI_LINE.match(line.strip())
            self.assertIsNotNone(match, repr(line))
            origin, token = match.group(1), match.group(2)
            port = int(origin.rsplit(":", 1)[1])
            for _ in range(200):
                if servers:
                    break
                time.sleep(0.05)
            self.assertTrue(servers)
            self.assertEqual(servers[0].port, port)
            status, _, payload = _fetch(servers[0], token, "GET", "/api/v1/snapshot")
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(payload)["schemaVersion"], 1)
            servers[0].shutdown()
            thread.join(15)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result.get("code"), 0)
        self.assertEqual(out.getvalue(), line)

    def test_cli_requires_a_run_root(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()) as err:
            with self.assertRaises(SystemExit) as ctx:
                run_console_cli.main([])
        self.assertEqual(ctx.exception.code, 2)
        self.assertNotIn("Traceback", err.getvalue())

    def test_cli_rejects_non_loopback_host(self) -> None:
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                run_console_cli.main([str(self.run_root), "--host", "localhost"])

    def test_cli_rejects_unknown_run_root_with_bounded_error(self) -> None:
        out = io.StringIO()
        err = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = run_console_cli.main([str(self.base / "missing")])
        self.assertEqual(code, 2)
        self.assertEqual(out.getvalue(), "")
        self.assertNotIn("Traceback", err.getvalue())
        self.assertNotIn(str(self.base), err.getvalue())


if __name__ == "__main__":
    unittest.main()
