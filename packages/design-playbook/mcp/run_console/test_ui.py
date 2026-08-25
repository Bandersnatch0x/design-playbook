#!/usr/bin/env python3
"""RCV1-007: the read-only Run Console UI resources (RED first).

Three groups of assertions without a browser:

1. Static analysis of the immutable UI triple (app.html / app.css /
   app.js): same-origin relative references only, no storage API, no
   service worker, no remote asset, no HTML-injection seam, fragment
   token stripped with history.replaceState, every authenticated request
   through the Authorization header, all dynamic text via textContent.
2. ``ui.py``: the exact-path static-resource table, content types, the
   per-resource Content-Security-Policy, construction fail-closed on a
   missing file, and byte immutability after construction.
3. ``http_server.py`` integration: token-less GET/HEAD on exactly the
   four UI routes serves the frozen bytes with the full security header
   policy; any request that carries an Authorization header keeps pure
   API semantics (so the read API is unchanged); queries, non-read
   methods, non-whitelisted and traversal paths never yield UI bytes or
   a directory listing; HEAD matches GET with no body.
"""
from __future__ import annotations

import http.client
import json
import sys
import tempfile
import unittest
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parents[2]
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

from design_playbook.mcp.run_console.http_server import (  # noqa: E402
    RunConsoleHTTPServer,
    serve_run_console,
)
from design_playbook.mcp.run_console.request_security import (  # noqa: E402
    ACTION_PAYLOAD_INVALID,
    METHOD_NOT_ALLOWED,
    ORIGIN_INVALID,
    ROUTE_NOT_FOUND,
    SESSION_TOKEN_INVALID,
)
from design_playbook.mcp.run_console.ui import (  # noqa: E402
    UIResources,
)

_DIR = Path(__file__).resolve().parent
_HTML = (_DIR / "app.html").read_text(encoding="utf-8")
_CSS = (_DIR / "app.css").read_text(encoding="utf-8")
_JS = (_DIR / "app.js").read_text(encoding="utf-8")
_UNSET = object()

# The UI is read-only: none of these identifiers may ever appear.
_FORBIDDEN_JS = (
    "localStorage",
    "sessionStorage",
    "document.cookie",
    "indexedDB",
    "serviceWorker",
    "innerHTML",
    "outerHTML",
    "insertAdjacentHTML",
    "document.write",
    "eval(",
    "new Function",
    "sendBeacon",
    "XMLHttpRequest",
    "WebSocket",
    "EventSource",
    "navigator.geolocation",
)


class UIStaticAnalysisTest(unittest.TestCase):
    """The immutable UI triple is self-contained and injection-free."""

    def test_html_references_only_relative_same_origin_assets(self) -> None:
        self.assertIn('href="app.css"', _HTML)
        self.assertIn('src="app.js"', _HTML)
        for text in (_HTML, _CSS, _JS):
            self.assertNotIn("http://", text)
            self.assertNotIn("https://", text)
            self.assertNotIn("src=\"//", text)
            self.assertNotIn("href=\"//", text)
            self.assertNotIn("url(//", text)
            self.assertNotIn("javascript:", text)

    def test_html_has_no_inline_handlers_or_frames(self) -> None:
        self.assertNotRegex(_HTML, r"\son[a-z]+\s*=")
        self.assertNotIn("<iframe", _HTML)
        self.assertNotIn("<object", _HTML)
        self.assertNotIn("<embed", _HTML)
        self.assertNotIn("<form", _HTML)

    def test_html_declares_language_and_viewport(self) -> None:
        self.assertIn('<html lang="en">', _HTML)
        self.assertIn('name="viewport"', _HTML)
        self.assertIn("<h1>", _HTML)

    def test_js_has_no_storage_remote_or_dom_injection_seams(self) -> None:
        for needle in _FORBIDDEN_JS:
            self.assertNotIn(needle, _JS, f"app.js must not use {needle}")

    def test_js_never_builds_remote_urls_or_cdn_modules(self) -> None:
        self.assertNotIn("import(", _JS)
        self.assertNotIn("document.createElement('script')", _JS)
        self.assertNotIn('document.createElement("script")', _JS)
        self.assertNotIn("document.createElement('link')", _JS)
        self.assertNotIn('document.createElement("link")', _JS)
        self.assertNotIn("http:", _JS)

    def test_js_token_and_request_contract(self) -> None:
        # Token only from the fragment, stripped from history immediately.
        self.assertIn("location.hash", _JS)
        self.assertIn("history.replaceState", _JS)
        # Every request is authenticated via the Authorization header.
        self.assertIn('"/api/v1/snapshot"', _JS)
        self.assertIn("Authorization", _JS)
        self.assertIn("Bearer", _JS)
        self.assertIn("cache: \"no-store\"", _JS)
        # All dynamic content is rendered as text, never as markup.
        self.assertIn("textContent", _JS)
        self.assertNotIn("createElement(\"a\")\n", _JS)

    def test_css_accessibility_basics(self) -> None:
        self.assertIn("prefers-reduced-motion", _CSS)
        self.assertIn(":focus-visible", _CSS)
        self.assertIn("overflow-wrap", _CSS)
        self.assertIn("min-width: 0", _CSS)


class UIResourcesTest(unittest.TestCase):
    """ui.py freezes the UI bytes at construction and maps exact paths."""

    def test_default_directory_is_the_package_directory(self) -> None:
        resources = UIResources()
        self.assertEqual(resources.directory, _DIR)
        shell = resources.lookup("/")
        assert shell is not None
        self.assertEqual(shell.body, (_DIR / "app.html").read_bytes())
        self.assertEqual(shell.content_type, "text/html; charset=utf-8")
        css = resources.lookup("/app.css")
        assert css is not None
        self.assertEqual(css.content_type, "text/css; charset=utf-8")
        js = resources.lookup("/app.js")
        assert js is not None
        self.assertEqual(js.content_type, "text/javascript; charset=utf-8")

    def test_csp_allows_only_self_css_js_and_connect_for_the_shell(self) -> None:
        shell = UIResources().lookup("/")
        assert shell is not None
        policy = shell.content_security_policy
        self.assertIn("default-src 'none'", policy)
        self.assertIn("style-src 'self'", policy)
        self.assertIn("script-src 'self'", policy)
        self.assertIn("connect-src 'self'", policy)
        self.assertIn("frame-ancestors 'none'", policy)
        self.assertIn("base-uri 'none'", policy)
        for asset in ("/app.css", "/app.js"):
            resource = UIResources().lookup(asset)
            assert resource is not None
            self.assertNotIn("style-src", resource.content_security_policy)
            self.assertNotIn("script-src", resource.content_security_policy)

    def test_lookup_is_exact_match_only(self) -> None:
        resources = UIResources()
        for path in (
            "/app.html/",
            "//app.css",
            "/APP.CSS",
            "/app.txt",
            "/run_console/",
            "/../app.html",
            "/%2e%2e/app.html",
            "/app.html%00",
            "",
            "/app.js?q=1",
        ):
            self.assertIsNone(resources.lookup(path), path)
        self.assertIsNone(resources.lookup(None))
        self.assertIsNone(resources.lookup(123))

    def test_missing_file_fails_closed_at_construction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "app.html").write_text("x", encoding="utf-8")
            with self.assertRaises(Exception):
                UIResources(directory=base)

    def test_bytes_are_immutable_after_construction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            for name in ("app.html", "app.css", "app.js"):
                (base / name).write_text("original-" + name, encoding="utf-8")
            resources = UIResources(directory=base)
            (base / "app.css").write_text("tampered", encoding="utf-8")
            css = resources.lookup("/app.css")
            assert css is not None
            self.assertEqual(css.body, b"original-app.css")


def _assert_error(payload: bytes, code: str) -> None:
    envelope = json.loads(payload)
    assert isinstance(envelope, dict)
    assert set(envelope) == {"schemaVersion", "error"}, set(envelope)
    assert envelope["error"]["code"] == code, envelope
    assert isinstance(envelope["error"]["retryable"], bool)


class StaticRouteTest(unittest.TestCase):
    """One real server per test; token-less requests hit the UI routes."""

    def setUp(self) -> None:
        from mcp.run_console import test_http_server as harness

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        base = Path(self._tmp.name).resolve()
        self.run_root = harness._make_root(base)
        self.session = harness.RunConsoleSession(
            run_root=self.run_root, package_root=_PKG_ROOT,
            now_fn=lambda: "2026-08-25T10:00:00Z",
        )
        self.server = serve_run_console(self.session, bind_host="127.0.0.1", port=0)
        self.addCleanup(self.server.stop)
        self.token = self.session.token
        self.origin = self.server.origin

    def _get(self, path, *, method="GET", token=_UNSET, origin=_UNSET, host=None):
        """One raw request; by default NO Authorization and NO Origin."""
        conn = http.client.HTTPConnection(
            self.server.bind_host, self.server.port, timeout=10
        )
        try:
            conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
            conn.putheader("Host", host or self.server.authority)
            if origin is not _UNSET:
                conn.putheader("Origin", origin)
            if token is not _UNSET:
                conn.putheader("Authorization", f"Bearer {token}")
            conn.endheaders()
            response = conn.getresponse()
            payload = response.read()
            fields = {k.lower(): v for k, v in response.getheaders()}
            return response.status, fields, payload
        finally:
            conn.close()

    # -- the shell itself ----------------------------------------------

    def test_root_serves_the_html_shell_tokenless(self) -> None:
        status, fields, body = self._get("/")
        self.assertEqual(status, 200)
        self.assertEqual(fields["content-type"], "text/html; charset=utf-8")
        self.assertEqual(body, (_DIR / "app.html").read_bytes())
        self.assertEqual(fields["server"], "RunConsole")

    def test_ui_assets_serve_with_exact_content_types(self) -> None:
        cases = {
            "/app.html": "text/html; charset=utf-8",
            "/app.css": "text/css; charset=utf-8",
            "/app.js": "text/javascript; charset=utf-8",
        }
        for path, content_type in cases.items():
            with self.subTest(path=path):
                status, fields, body = self._get(path)
                self.assertEqual(status, 200)
                self.assertEqual(fields["content-type"], content_type)
                self.assertEqual(body, (_DIR / path.lstrip("/")).read_bytes())

    def test_ui_responses_carry_the_full_header_policy(self) -> None:
        for path in ("/", "/app.css", "/app.js"):
            with self.subTest(path=path):
                _, fields, _ = self._get(path)
                self.assertEqual(fields["x-content-type-options"], "nosniff")
                self.assertEqual(fields["cache-control"], "no-store")
                self.assertIn("frame-ancestors 'none'", fields["content-security-policy"])
                for name, value in fields.items():
                    self.assertFalse(name.startswith("access-control-"), name)
        _, fields, _ = self._get("/")
        self.assertIn("style-src 'self'", fields["content-security-policy"])
        self.assertIn("script-src 'self'", fields["content-security-policy"])
        self.assertIn("connect-src 'self'", fields["content-security-policy"])

    def test_head_matches_get_without_a_body(self) -> None:
        get_status, get_fields, get_body = self._get("/")
        head_status, head_fields, head_body = self._get("/", method="HEAD")
        self.assertEqual(get_status, head_status)
        self.assertEqual(get_fields["content-length"], head_fields["content-length"])
        self.assertEqual(head_body, b"")
        self.assertGreater(len(get_body), 0)

    def test_exact_same_origin_is_allowed_foreign_origin_rejected(self) -> None:
        status, _, _ = self._get("/", origin=self.origin)
        self.assertEqual(status, 200)
        status, _, payload = self._get("/", origin="http://evil.example")
        self.assertEqual(status, 403)
        _assert_error(payload, ORIGIN_INVALID)

    def test_wrong_host_is_rejected_before_the_shell(self) -> None:
        status, _, payload = self._get("/", host="evil.example:80")
        self.assertEqual(status, 403)
        _assert_error(payload, ORIGIN_INVALID)

    # -- authenticated requests keep pure API semantics -----------------

    def test_authenticated_request_to_ui_paths_is_route_not_found(self) -> None:
        # An authenticated client is an API client: / is not an API route.
        for path in ("/", "/app.html", "/app.css", "/app.js"):
            with self.subTest(path=path):
                status, _, payload = self._get(path, token=self.token)
                self.assertEqual(status, 404)
                _assert_error(payload, ROUTE_NOT_FOUND)

    def test_invalid_bearer_on_ui_path_is_not_served_the_shell(self) -> None:
        status, _, payload = self._get("/", token="not-the-token")
        self.assertEqual(status, 401)
        _assert_error(payload, SESSION_TOKEN_INVALID)

    # -- strictness: queries, methods, unknown paths ---------------------

    def test_ui_routes_accept_no_query_parameters(self) -> None:
        status, _, payload = self._get("/?x=1")
        self.assertEqual(status, 400)
        _assert_error(payload, ACTION_PAYLOAD_INVALID)

    def test_token_in_query_is_rejected_before_any_ui_serving(self) -> None:
        status, _, payload = self._get(f"/?token={self.token}")
        self.assertEqual(status, 401)
        _assert_error(payload, SESSION_TOKEN_INVALID)
        status, _, payload = self._get(f"/app.js?token={self.token}")
        self.assertEqual(status, 401)
        _assert_error(payload, SESSION_TOKEN_INVALID)

    def test_non_read_methods_on_ui_paths_are_405(self) -> None:
        # Non-read methods must present the exact Origin (S25); with it,
        # the UI route answers 405 like every other non-read route.
        for method in ("POST", "PUT", "DELETE", "PATCH"):
            with self.subTest(method=method):
                status, fields, payload = self._get(
                    "/", method=method, origin=self.origin
                )
                self.assertEqual(status, 405)
                self.assertEqual(fields.get("allow"), "GET, HEAD")
                _assert_error(payload, METHOD_NOT_ALLOWED)
        status, _, payload = self._get("/", method="POST")  # no Origin
        self.assertEqual(status, 403)
        _assert_error(payload, ORIGIN_INVALID)

    def test_unknown_and_traversal_paths_never_yield_ui_bytes(self) -> None:
        paths = (
            "/favicon.ico",
            "/app.txt",
            "/app.css/",
            "/APP.CSS",
            "/run_console/",
            "/run_console/app.html",
            "/../app.html",
            "/%2e%2e/app.html",
            "/..%2fapp.html",
            "/app.html%00",
            "/app.js%20",
        )
        for path in paths:
            with self.subTest(path=path):
                status, _, payload = self._get(path)
                self.assertEqual(status, 401)
                _assert_error(payload, SESSION_TOKEN_INVALID)
                self.assertNotIn(b"<", payload)

    def test_protocol_relative_path_serves_only_the_whitelisted_resource(self) -> None:
        # http.client collapses "//x"; assert the raw wire form directly.
        # The stdlib request parser also collapses the leading "//", so the
        # protocol-relative form resolves to the same frozen app.css bytes:
        # still the whitelist, never a listing or a filesystem path.
        slash = chr(47)
        request = (
            "GET " + slash + slash + "app.css HTTP/1.1\r\n" +
            "Host: " + self.server.authority + "\r\nConnection: close\r\n\r\n"
        ).encode("ascii")
        import socket

        with socket.create_connection(
            (self.server.bind_host, self.server.port), timeout=5
        ) as sock:
            sock.sendall(request)
            chunks = []
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
        payload = b"".join(chunks)
        self.assertIn(b" 200 ", payload.split(b"\r\n", 1)[0])
        self.assertIn(b"text/css", payload)
        self.assertTrue(payload.endswith((_DIR / "app.css").read_bytes()))

    def test_no_directory_listing_exists(self) -> None:
        for path in ("/run_console/", "/fixtures/", "/evidence/"):
            with self.subTest(path=path):
                # Token-less: fail closed before routing; with a token: not
                # a route. Either way a bounded JSON error, never a listing.
                status, _, payload = self._get(path)
                self.assertEqual(status, 401)
                _assert_error(payload, SESSION_TOKEN_INVALID)
                status, _, payload = self._get(path, token=self.token)
                self.assertEqual(status, 404)
                _assert_error(payload, ROUTE_NOT_FOUND)
                self.assertNotIn(b"<html", payload)
                self.assertNotIn(b"Directory", payload)

    # -- immutability at the HTTP boundary -------------------------------

    def test_served_ui_bytes_are_frozen_at_server_start(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            for name in ("app.html", "app.css", "app.js"):
                (base / name).write_text("frozen-" + name, encoding="utf-8")
            server = RunConsoleHTTPServer(
                self.session, bind_host="127.0.0.1", port=0, ui_directory=base
            )
            server.start_serving()
            self.addCleanup(server.stop)
            conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=10)
            try:
                conn.request("GET", "/app.css", headers={"Host": server.authority})
                body = conn.getresponse().read()
            finally:
                conn.close()
            self.assertEqual(body, b"frozen-app.css")
            (base / "app.css").write_text("tampered-after-start", encoding="utf-8")
            conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=10)
            try:
                conn.request("GET", "/app.css", headers={"Host": server.authority})
                body = conn.getresponse().read()
            finally:
                conn.close()
            self.assertEqual(body, b"frozen-app.css")


if __name__ == "__main__":
    unittest.main()
