#!/usr/bin/env python3
"""G5 trust-boundary isolation tests for the preview browser control.

Covers the secure-ship 0.4.4 ticket 01 acceptance:

- prototype HTML isolated inside ``<iframe sandbox="allow-scripts" srcdoc="...">``
  with ``allow-same-origin`` deliberately omitted (parent DOM unreachable by
  prototype scripts, so the hidden decision token stays secret).
- one-time decision token generated via ``secrets.token_urlsafe(32)`` and bound
  to the preview round + a first-decision-wins session.
- ``do_POST`` fails closed (``confirmed=False``, ``floor_pass=False``) on the
  three rejection paths: token missing, token reused, round mismatch.
- a normal human confirm with the token still records ``confirmed=True`` and
  ``floor_pass=True``; ``_write_confirm`` still records ``prototype_html_hash``.
"""
from __future__ import annotations

import json
import re
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Any
from unittest import mock
from urllib.parse import urlencode

# Sibling modules resolve via the test file's directory (pytest prepend mode
# or sys.path[0] under plain `python <file>`); same convention as
# test_server_stdio.py.
import browser  # noqa: E402
from confirm import (  # noqa: E402
    _DecisionSession,
    _generate_decision_token,
    _write_confirm,
)


# --------------------------------------------------------------------------- #
# HTTP client helpers (raw sockets, mirroring test_server_stdio.py)            #
# --------------------------------------------------------------------------- #


def _stash_http(server_module: Any) -> tuple[type, dict[str, int]]:
    """Wrap HTTPServer so the bound port is exposed to the client thread."""
    real = server_module.HTTPServer
    port_box: dict[str, int] = {}

    class StashingHTTPServer(real):  # type: ignore[misc, valid-type]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            port_box["port"] = self.server_address[1]

    return StashingHTTPServer, port_box


def _wait_for_port(port_box: dict[str, int], deadline: float = 5.0) -> int | None:
    end = time.time() + deadline
    while time.time() < end:
        port = port_box.get("port")
        if port:
            return port
        time.sleep(0.01)
    return None


def _http_round_trip(port: int, raw_request: bytes) -> bytes:
    with socket.create_connection(("127.0.0.1", port), timeout=3) as sock:
        sock.sendall(raw_request)
        sock.settimeout(3)
        chunks: list[bytes] = []
        try:
            while True:
                data = sock.recv(65536)
                if not data:
                    break
                chunks.append(data)
        except socket.timeout:
            pass
        return b"".join(chunks)


def _get_page(port: int) -> str:
    req = (
        f"GET / HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nConnection: close\r\n\r\n"
    ).encode("ascii")
    return _http_round_trip(port, req).decode("utf-8", errors="replace")


def _post_form(port: int, fields: dict[str, str]) -> bytes:
    body = urlencode(fields).encode("ascii")
    req = (
        f"POST /decide HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\n"
        "Content-Type: application/x-www-form-urlencoded\r\n"
        f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n"
    ).encode("ascii") + body
    return _http_round_trip(port, req)


def _extract_token(page: str) -> str | None:
    m = re.search(r'name="dpb_token"\s+value="([^"]+)"', page)
    return m.group(1) if m else None


def _run_collect(
    proto_html: str,
    client_fn: Any,
    *,
    summary: str = "summary",
    options: list[str] | None = None,
    round_n: int = 1,
) -> dict[str, Any]:
    """Drive browser._collect_via_browser with a mocked owned window.

    ``client_fn(port)`` runs in a thread and is expected to POST something to
    /decide so the collect call terminates.
    """
    if options is None:
        options = ["确认通过", "需要修改"]
    StashingHTTPServer, port_box = _stash_http(browser)

    def client_wrapper() -> None:
        port = _wait_for_port(port_box)
        if not port:
            return
        try:
            client_fn(port)
        except Exception as exc:  # noqa: BLE001
            # Surface client-side failures for the main thread; do not hang.
            port_box["client_error"] = repr(exc)

    client_thread = threading.Thread(target=client_wrapper, daemon=True)
    client_thread.start()

    with tempfile.TemporaryDirectory() as tmp:
        proto = Path(tmp) / "proto.html"
        proto.write_text(proto_html, encoding="utf-8")
        with mock.patch.object(browser, "HTTPServer", StashingHTTPServer), mock.patch.object(
            browser, "_open_preview_window", return_value=(None, None)
        ), mock.patch.object(
            browser, "_request_browser_window_close"
        ), mock.patch.object(
            browser, "_kill_browser_proc"
        ), mock.patch.object(browser, "_rm_tree"):
            decision = browser._collect_via_browser(proto, summary, options, round_n)

    client_thread.join(timeout=3)
    assert not client_thread.is_alive(), "client thread still alive"
    client_error = port_box.get("client_error")
    assert not client_error, f"client thread error: {client_error}"
    return decision


# --------------------------------------------------------------------------- #
# Unit tests: token + session logic                                           #
# --------------------------------------------------------------------------- #


class DecisionTokenUnitTests(unittest.TestCase):
    def test_token_is_urlsafe_unique_and_long(self) -> None:
        a = _generate_decision_token()
        b = _generate_decision_token()
        self.assertNotEqual(a, b)
        # secrets.token_urlsafe(32) yields ~43 chars of [A-Za-z0-9_-]
        self.assertGreaterEqual(len(a), 32)
        self.assertRegex(a, r"^[A-Za-z0-9_-]+$")

    def test_missing_token_rejected(self) -> None:
        session = _DecisionSession(1, _generate_decision_token())
        self.assertFalse(session.validate(1, None))
        self.assertEqual(session.last_rejection, "missing")
        self.assertFalse(session.validate(1, ""))
        self.assertEqual(session.last_rejection, "missing")
        self.assertFalse(session.locked)

    def test_round_mismatch_rejected(self) -> None:
        token = _generate_decision_token()
        session = _DecisionSession(1, token)
        self.assertFalse(session.validate(2, token))
        self.assertEqual(session.last_rejection, "round_mismatch")
        # A failed attempt must not consume the session.
        self.assertTrue(session.validate(1, token))

    def test_invalid_token_rejected(self) -> None:
        session = _DecisionSession(1, _generate_decision_token())
        self.assertFalse(session.validate(1, "not-the-real-token"))
        self.assertEqual(session.last_rejection, "invalid_token")
        self.assertFalse(session.locked)

    def test_reuse_rejected_after_first_valid(self) -> None:
        token = _generate_decision_token()
        session = _DecisionSession(1, token)
        self.assertTrue(session.validate(1, token))
        self.assertTrue(session.locked)
        # Second POST with the same token (replay) is rejected.
        self.assertFalse(session.validate(1, token))
        self.assertEqual(session.last_rejection, "reuse")
        # Even a different token is rejected once locked.
        self.assertFalse(session.validate(1, "other"))


# --------------------------------------------------------------------------- #
# Integration tests: parent-page rendering + HTTP decide flow                 #
# --------------------------------------------------------------------------- #


class TrustBoundaryIntegrationTests(unittest.TestCase):
    def test_iframe_sandbox_excludes_allow_same_origin(self) -> None:
        page_box: dict[str, str] = {"page": ""}

        def client(port: int) -> None:
            page = _get_page(port)
            page_box["page"] = page
            token = _extract_token(page) or ""
            _post_form(
                port,
                {
                    "choice": "确认通过",
                    "feedback": "ok",
                    "anchors_json": "[]",
                    "dpb_token": token,
                    "dpb_round": "1",
                },
            )

        _run_collect(
            "<html><body><h1>proto-marker-123</h1></body></html>", client
        )
        page = page_box["page"]
        self.assertIn("srcdoc=", page)
        m = re.search(r'<iframe[^>]*\bsandbox="([^"]*)"', page)
        self.assertIsNotNone(m, f"no sandboxed iframe in page head: {page[:240]!r}")
        sandbox_attr = m.group(1)
        self.assertIn("allow-scripts", sandbox_attr)
        self.assertNotIn(
            "allow-same-origin",
            sandbox_attr,
            "allow-same-origin would re-same-origin the iframe and defeat G5",
        )
        # The prototype body must NOT be rendered inline in the parent document;
        # it lives escaped inside the iframe srcdoc attribute.
        self.assertNotIn("<h1>proto-marker-123</h1>", page)
        self.assertIn("proto-marker-123", page)

    def test_control_form_carries_hidden_token_and_round(self) -> None:
        page_box: dict[str, str] = {"page": ""}

        def client(port: int) -> None:
            page_box["page"] = _get_page(port)
            token = _extract_token(page_box["page"]) or ""
            _post_form(
                port,
                {
                    "choice": "确认通过",
                    "feedback": "ok",
                    "anchors_json": "[]",
                    "dpb_token": token,
                    "dpb_round": "1",
                },
            )

        _run_collect("<html><body>x</body></html>", client)
        page = page_box["page"]
        token = _extract_token(page)
        self.assertIsNotNone(token, "hidden dpb_token field missing from control form")
        self.assertGreaterEqual(len(token), 32)
        self.assertRegex(
            page,
            r'name="dpb_round"\s+value="1"',
            "hidden dpb_round field missing or wrong round",
        )

    def test_malicious_post_without_token_does_not_hijack_session(self) -> None:
        """MEDIUM-1 (secure-ship-0.4.4): a forged no-token POST must NOT
        terminate the preview session.

        A sandboxed prototype forging ``fetch('/decide', ...)`` arrives
        without ``dpb_token`` (the hidden field lives in the trusted parent,
        unreachable from the iframe). The server still fail-closes the
        result internally (``confirmed=False``, ``rejected=True``) AND
        responds 200, but it must keep the session alive so the real user
        can still click confirm. Before MEDIUM-1, ``done.set()`` fired
        unconditionally and one forged POST aborted every preview before
        the user clicked anything (DoS on the gate).
        """

        def client(port: int) -> None:
            # 1) Forged cross-origin POST: no dpb_token, no dpb_round.
            _post_form(
                port,
                {
                    "choice": "确认通过",
                    "feedback": "forged",
                    "anchors_json": "[]",
                },
            )
            # 2) Real user then submits via the trusted control form, which
            #    is the path that should terminate the session.
            page = _get_page(port)
            token = _extract_token(page) or ""
            _post_form(
                port,
                {
                    "choice": "确认通过",
                    "feedback": "real user clicked confirm",
                    "anchors_json": "[]",
                    "dpb_token": token,
                    "dpb_round": "1",
                },
            )

        decision = _run_collect(
            "<html><body><script>fetch('/decide',{method:'POST',"
            "body:new URLSearchParams({choice:'CONFIRM',feedback:'ok'})})"
            "</script></body></html>",
            client,
        )
        # Forged POST did not hijack: real user's confirm is the final decision.
        self.assertTrue(decision["confirmed"])
        self.assertTrue(decision["floor_pass"])
        self.assertEqual(decision["selected_options"], ["确认通过"])
        self.assertNotIn("rejected", decision)

    def test_round_mismatch_rejected_at_http(self) -> None:
        # A POST whose dpb_round does not match the session round is rejected
        # (validate -> round_mismatch) and, per MEDIUM-1, must NOT end the
        # session - the real user can still confirm afterward. The mismatch
        # POST is fail closed internally; the subsequent valid POST wins,
        # proving the mismatch neither consumed nor hijacked the session.
        def client(port: int) -> None:
            page = _get_page(port)
            token = _extract_token(page) or ""
            # 1) Mismatched-round POST: rejected, must not terminate.
            _post_form(
                port,
                {
                    "choice": "确认通过",
                    "feedback": "ok",
                    "anchors_json": "[]",
                    "dpb_token": token,
                    "dpb_round": "99",
                },
            )
            # 2) Real user's valid-round POST: must still confirm.
            _post_form(
                port,
                {
                    "choice": "确认通过",
                    "feedback": "real user",
                    "anchors_json": "[]",
                    "dpb_token": token,
                    "dpb_round": "1",
                },
            )

        decision = _run_collect("<html><body>x</body></html>", client)
        # Mismatch did not hijack: the real user's valid POST wins.
        self.assertTrue(decision["confirmed"])
        self.assertEqual(decision["selected_options"], ["确认通过"])
        self.assertFalse(decision.get("aborted"))

    def test_normal_confirm_with_token_passes(self) -> None:
        def client(port: int) -> None:
            page = _get_page(port)
            token = _extract_token(page)
            assert token, "token not rendered in control form"
            _post_form(
                port,
                {
                    "choice": "确认通过",
                    "feedback": "looks good, ship it",
                    "anchors_json": "[]",
                    "dpb_token": token,
                    "dpb_round": "1",
                },
            )

        decision = _run_collect(
            "<html><body><h1>real prototype</h1></body></html>", client
        )
        self.assertTrue(decision["confirmed"])
        self.assertEqual(decision["selected_options"], ["确认通过"])
        self.assertTrue(decision["floor_pass"])
        self.assertFalse(decision["aborted"])
        self.assertNotIn("rejected", decision)

    def test_abort_with_token_is_recorded(self) -> None:
        def client(port: int) -> None:
            page = _get_page(port)
            token = _extract_token(page) or ""
            _post_form(
                port,
                {
                    "choice": "__abort__",
                    "feedback": "",
                    "anchors_json": "[]",
                    "dpb_token": token,
                    "dpb_round": "1",
                },
            )

        decision = _run_collect("<html><body>x</body></html>", client)
        self.assertFalse(decision["confirmed"])
        self.assertTrue(decision["aborted"])
        self.assertNotIn("rejected", decision)


# --------------------------------------------------------------------------- #
# Confirm record hash (existing trusted-side behavior unchanged)             #
# --------------------------------------------------------------------------- #


class ConfirmRecordHashTests(unittest.TestCase):
    def test_write_confirm_records_prototype_html_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            preview_dir = Path(tmp)
            proto = preview_dir / "round-1.html"
            proto_bytes = b"<html><body><h1>hash me</h1></body></html>"
            proto.write_bytes(proto_bytes)
            import hashlib

            expected = hashlib.sha256(proto_bytes).hexdigest()

            out = _write_confirm(
                preview_dir,
                round_n=1,
                report_ref="report.md",
                selected=["确认通过"],
                feedback="ok",
                prototype=proto,
                confirmed=True,
                floor_pass=True,
            )
            record = json.loads(out.read_text(encoding="utf-8"))

        self.assertTrue(record["confirmed"])
        self.assertTrue(record["floor_pass"])
        self.assertEqual(record["prototype_html_hash"], expected)
        self.assertEqual(record["round"], 1)


if __name__ == "__main__":
    unittest.main()
